"""Top-level orchestration.

Inputs (duck-typed):
- board: any object exposing `tiles: ndarray[Tile]` (rows, cols) and an
         iterable `rivers` of objects whose `getTiles() -> (Tile, Tile)`.
- starting_city: dict-like with keys
        center  : (col, row)
        hansa   : (col, row)
        commhub : (col, row)
        harbor  : (col, row) | None
        aqueduct: (col, row) | None
- n: number of new cities to place
- mode: 'hansa_only' or 'combination'
- exchange_rate: float, used in combination mode
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

from .bnb import branch_and_bound, objective
from .candidates import (annotate_synergy, aqueduct_enum_limited, build_city,
                         enumerate_city_centers, rank_stars)
from .cluster import build_clusters
from .features import extract_features
from .hex import Coord, distance
from .model import (AQ, CH, H, HANSA_ONLY, HB,
                    Assignment, City, CityResult, Cluster, Score, Solution)
from .scoring import compute_influence_field, score_ch_at, score_hansa_at, score_hb_at

STAR_TRY_BUDGET_DEFAULT = 1
AQ_TRY_BUDGET_DEFAULT = 2
ProgressCallback = Callable[[int, int, str], None]
ClusterPlan = Tuple[Dict[int, Optional[Coord]], List[Coord]]


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


def _intrinsic_value(city: City,
                     influence: Dict[Coord, int]) -> float:
    """A cheap score used to pick which N candidates to keep."""
    if not city.hansa_candidates:
        return float("-inf")
    base = max(influence.get(t, 0) for t in city.hansa_candidates)
    # Triangle potential: +2 (CH adjacent), +2 if Aq possible, +2 if coastal.
    triangle = 2 + (2 if city.aqueduct_candidates else 0) + (2 if city.coastal_flag else 0)
    return base + triangle


def _pick_n_candidates(candidates: List[City], n: int,
                       fixed_centers: List[Coord],
                       influence: Dict[Coord, int],
                       min_spacing: int = 4) -> List[City]:
    """Greedy: pick the top-scoring candidates respecting pairwise ≥ 4 spacing
    among the chosen set (and against fixed centers, already enforced upstream).
    """
    if n <= 0:
        return []
    ranked = sorted(candidates,
                    key=lambda c: -_intrinsic_value(c, influence))
    chosen: List[City] = []
    chosen_coords: List[Coord] = list(fixed_centers)
    for c in ranked:
        if len(chosen) >= n:
            break
        if any(distance(c.coords, ec) < min_spacing for ec in chosen_coords):
            continue
        chosen.append(c)
        chosen_coords.append(c.coords)
    return chosen


def _attach_starting_city(clusters: List[Cluster],
                          starting: Optional[City]) -> List[Cluster]:
    """Attach the fixed-center starting city to the interacting cluster set.

    If it overlaps one or more clusters, fuse them so joint search sees all
    cross-city adjacencies. Otherwise keep the starting city as a standalone
    cluster so its own districts are still optimized.
    """
    if starting is None:
        return clusters
    INTERACT = 6
    overlap_idx = [
        i for i, cl in enumerate(clusters)
        if any(distance(starting.coords, c.coords) <= INTERACT for c in cl.cities)
    ]
    if not overlap_idx:
        return clusters + [Cluster(cities=[starting])]
    merged_cities: List[City] = [starting]
    for i in overlap_idx:
        merged_cities.extend(clusters[i].cities)
    keep = [cl for j, cl in enumerate(clusters) if j not in overlap_idx]
    keep.append(Cluster(cities=merged_cities))
    return keep


def _solve_cluster(
    cluster: Cluster,
    plans: List[ClusterPlan],
    feature_map,
    influence: Dict[Coord, int],
    mode: str,
    w: float,
    progress_callback: Optional[ProgressCallback] = None,
    progress_state: Optional[Dict[str, int]] = None,
    cluster_idx: int = 1,
    cluster_count: int = 1,
) -> Tuple[Dict[int, Assignment], Score]:
    best_assign: Optional[Dict[int, Assignment]] = None
    best_score = Score()
    best_obj = float("-inf")

    for alpha_idx, (alpha, stars) in enumerate(plans, start=1):
        # Score the no-star baseline first — it acts as a hard floor.
        no_star_assign, no_star_score = branch_and_bound(
            cluster, alpha, star=None, feature_map=feature_map,
            influence=influence, lower_bound=None, mode=mode, w=w,
        )
        _tick_progress(
            progress_callback,
            progress_state,
            f"cluster {cluster_idx}/{cluster_count} alpha {alpha_idx}/{len(plans)} baseline",
        )
        if objective(no_star_score, mode, w) > best_obj:
            best_obj = objective(no_star_score, mode, w)
            best_assign = no_star_assign
            best_score = no_star_score

        for star_idx, T in enumerate(stars, start=1):
            star_assign, star_score = branch_and_bound(
                cluster, alpha, star=T, feature_map=feature_map,
                influence=influence,
                lower_bound=(no_star_assign, no_star_score),
                mode=mode, w=w,
            )
            _tick_progress(
                progress_callback,
                progress_state,
                f"cluster {cluster_idx}/{cluster_count} alpha {alpha_idx}/{len(plans)} "
                f"star {star_idx}/{len(stars)}",
            )
            if objective(star_score, mode, w) > best_obj:
                best_obj = objective(star_score, mode, w)
                best_assign = star_assign
                best_score = star_score

    if best_assign is None:
        # Single-city cluster with no working candidates — return empty.
        best_assign = {i: Assignment() for i, _ in enumerate(cluster.cities)}
    return best_assign, best_score


def _cluster_search_plan(
    cluster: Cluster,
    feature_map,
    influence: Dict[Coord, int],
    star_try_budget: int,
    aqueduct_try_budget: Optional[int],
) -> List[ClusterPlan]:
    plans: List[ClusterPlan] = []
    for alpha in aqueduct_enum_limited(cluster, influence, aqueduct_try_budget):
        ranked = rank_stars(cluster, alpha, feature_map, influence)
        stars = [T for T, _ub, _k in ranked[:star_try_budget]]
        plans.append((alpha, stars))
    return plans


def _plan_steps(plans: List[ClusterPlan]) -> int:
    return sum(1 + len(stars) for _alpha, stars in plans)


def _tick_progress(
    progress_callback: Optional[ProgressCallback],
    progress_state: Optional[Dict[str, int]],
    message: str,
) -> None:
    if progress_callback is None or progress_state is None:
        return
    progress_state["completed"] += 1
    progress_callback(progress_state["completed"], progress_state["total"], message)


def solve(
    board: Any,
    starting_city: Optional[Dict[str, Any]],
    n: int,
    mode: str = HANSA_ONLY,
    exchange_rate: float = 1.0,
    star_try_budget: int = STAR_TRY_BUDGET_DEFAULT,
    aqueduct_try_budget: Optional[int] = AQ_TRY_BUDGET_DEFAULT,
    progress_callback: Optional[ProgressCallback] = None,
) -> Solution:
    """Run Solution A on the given board.

    Returns a `Solution` with per-city assignments and a total score.
    """
    feature_map = extract_features(board)
    influence = compute_influence_field(feature_map)

    starting = _build_starting_city(starting_city, feature_map)
    fixed_centers: List[Coord] = [starting.coords] if starting else []

    candidates = enumerate_city_centers(feature_map, fixed_centers)
    annotate_synergy(candidates, fixed_centers)

    chosen = _pick_n_candidates(candidates, n, fixed_centers, influence)
    if not chosen and starting is None:
        return Solution(cities=[], score=Score(), mode=mode,
                        exchange_rate=exchange_rate)

    clusters = build_clusters(chosen) if chosen else []
    clusters = _attach_starting_city(clusters, starting)

    cluster_work = [
        (
            cluster,
            _cluster_search_plan(
                cluster,
                feature_map,
                influence,
                star_try_budget,
                aqueduct_try_budget,
            ),
        )
        for cluster in clusters
    ]
    total_steps = sum(_plan_steps(plans) for _cluster, plans in cluster_work)
    if progress_callback is not None:
        progress_callback(0, max(1, total_steps), "planning complete")

    total_score = Score()
    city_results: List[CityResult] = []
    progress_state = {"completed": 0, "total": max(1, total_steps)}

    for cluster_idx, (cluster, plans) in enumerate(cluster_work, start=1):
        assignments, cluster_score = _solve_cluster(
            cluster,
            plans,
            feature_map,
            influence,
            mode,
            exchange_rate,
            progress_callback=progress_callback,
            progress_state=progress_state,
            cluster_idx=cluster_idx,
            cluster_count=len(cluster_work),
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

    return Solution(
        cities=city_results,
        score=total_score,
        mode=mode,
        exchange_rate=exchange_rate,
    )
