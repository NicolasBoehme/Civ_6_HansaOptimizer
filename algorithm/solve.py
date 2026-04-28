"""Top-level orchestration.

Inputs (duck-typed):
- board: any object exposing `tiles: ndarray[Tile]` (rows, cols) and an
         iterable `rivers` of objects whose `getTiles() -> (Tile, Tile)`.
- starting_city: dict-like with keys
        center  : (col, row)
        hansa   : (col, row) | None
        commhub : (col, row) | None
        harbor  : (col, row) | None
        aqueduct: (col, row) | None
- n: number of new cities to place
- mode: 'hansa_only' or 'combination'
- exchange_rate: float, used in combination mode

Pipeline (deliberately flat — one BnB call per cluster, nothing else):
1. Extract tile features and the influence field.
2. Enumerate candidate city centers, then greedily pick N.
3. Cluster the N picks (plus the starting city) by interaction radius.
4. For each cluster, run the single-pass BnB in `bnb.solve_cluster`.
5. Reassemble per-city scores from the final ownership map.
"""
from typing import Any, Callable, Dict, List, Optional

from .bnb import solve_cluster
from .candidates import build_city, enumerate_city_centers
from .cluster import build_clusters
from .features import extract_features
from .hex import Coord, distance
from .model import (AQ, CH, H, HANSA_ONLY, HB,
                    Assignment, City, CityResult, Cluster, Score, Solution)
from .scoring import (compute_influence_field, score_ch_at,
                      score_hansa_at, score_hb_at)

ProgressCallback = Callable[[int, int, str], None]
INTERACTION_RADIUS = 6


def _build_starting_city(spec: Optional[Dict[str, Any]],
                         feature_map) -> Optional[City]:
    if spec is None:
        return None
    center: Coord = spec["center"]
    fixed = Assignment(
        hansa=spec.get("hansa"),
        commhub=spec.get("commhub"),
        harbor=spec.get("harbor"),
        aqueduct=spec.get("aqueduct"),
    )
    city = build_city(center, feature_map, is_existing=False)
    city.fixed_assignment = fixed
    return city


def _intrinsic_value(city: City, influence: Dict[Coord, int]) -> float:
    if not city.hansa_candidates:
        return float("-inf")
    base = max(influence.get(t, 0) for t in city.hansa_candidates)
    triangle = 2 + (2 if city.aqueduct_candidates else 0) \
                 + (2 if city.coastal_flag else 0)
    return base + triangle


def _pick_n_centers(candidates: List[City], n: int,
                    fixed_centers: List[Coord],
                    influence: Dict[Coord, int],
                    min_spacing: int = 4) -> List[City]:
    if n <= 0:
        return []
    ranked = sorted(candidates, key=lambda c: -_intrinsic_value(c, influence))
    chosen: List[City] = []
    taken: List[Coord] = list(fixed_centers)
    for c in ranked:
        if len(chosen) >= n:
            break
        if any(distance(c.coords, ec) < min_spacing for ec in taken):
            continue
        chosen.append(c)
        taken.append(c.coords)
    return chosen


def _attach_starting(clusters: List[Cluster],
                     starting: City) -> List[Cluster]:
    overlap = [
        i for i, cl in enumerate(clusters)
        if any(distance(starting.coords, c.coords) <= INTERACTION_RADIUS
               for c in cl.cities)
    ]
    if not overlap:
        return clusters + [Cluster(cities=[starting])]
    merged: List[City] = [starting]
    for i in overlap:
        merged.extend(clusters[i].cities)
    keep = [cl for j, cl in enumerate(clusters) if j not in overlap]
    keep.append(Cluster(cities=merged))
    return keep


def solve(
    board: Any,
    starting_city: Optional[Dict[str, Any]],
    n: int,
    mode: str = HANSA_ONLY,
    exchange_rate: float = 1.0,
    progress_callback: Optional[ProgressCallback] = None,
) -> Solution:
    feature_map = extract_features(board)
    influence = compute_influence_field(feature_map)

    starting = _build_starting_city(starting_city, feature_map)
    fixed_centers: List[Coord] = [starting.coords] if starting else []

    candidates = enumerate_city_centers(feature_map, fixed_centers)
    chosen = _pick_n_centers(candidates, n, fixed_centers, influence)

    if not chosen and starting is None:
        return Solution(cities=[], score=Score(), mode=mode,
                        exchange_rate=exchange_rate)

    clusters = build_clusters(chosen) if chosen else []
    if starting is not None:
        clusters = _attach_starting(clusters, starting)

    total = max(1, len(clusters))
    if progress_callback is not None:
        progress_callback(0, total, "starting")

    total_score = Score()
    city_results: List[CityResult] = []

    for idx, cluster in enumerate(clusters, start=1):
        assignments, cluster_score = solve_cluster(
            cluster, feature_map, mode, exchange_rate,
        )
        owners = {}
        for ci, a in assignments.items():
            for kind, t in ((H, a.hansa), (CH, a.commhub),
                            (HB, a.harbor), (AQ, a.aqueduct)):
                if t is not None:
                    owners[t] = (ci, kind)
        for ci, city in enumerate(cluster.cities):
            a = assignments.get(ci, Assignment())
            prod = score_hansa_at(a.hansa, feature_map, owners) if a.hansa else 0
            gold = 0
            if a.commhub is not None:
                gold += score_ch_at(a.commhub, feature_map, owners)
            if a.harbor is not None:
                gold += score_hb_at(a.harbor, feature_map, owners)
            city_results.append(CityResult(
                city=city, assignment=a, score=Score(prod, gold)))
        total_score = total_score + cluster_score
        if progress_callback is not None:
            progress_callback(idx, total, f"cluster {idx}/{total}")

    return Solution(
        cities=city_results,
        score=total_score,
        mode=mode,
        exchange_rate=exchange_rate,
    )
