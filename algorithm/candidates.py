"""Candidate generation:

Phase 1 — city-center candidates and per-city candidate sets.
Phase 3 — aqueduct enumeration over a cluster.
Phase 4 — star-center identification + ranking.
"""
from itertools import product
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .features import FeatureMap
from .hex import Coord, distance, disk, neighbours
from .model import AQ, CH, H, HB, City, Cluster


def _district_fixed(city: City, kind: str) -> bool:
    if city.fixed_assignment is None:
        return False
    value = getattr(city.fixed_assignment, {
        H: "hansa",
        CH: "commhub",
        HB: "harbor",
        AQ: "aqueduct",
    }[kind])
    if value is not None:
        return True
    return city.is_existing


# --- Phase 1: city-center filtering ------------------------------------------

def _aqueduct_candidates_for(center: Coord, feature_map: FeatureMap) -> List[Coord]:
    """Tiles within distance 1 of center that are placeable AND adjacent to
    river / lake / mountain.
    """
    out = []
    for n in neighbours(center):
        feat = feature_map.get(n)
        if feat is None or not feat.placeable:
            continue
        if feat.aqueduct_feature:
            out.append(n)
    return out


def _placeable_in_radius(center: Coord, r: int,
                         feature_map: FeatureMap) -> List[Coord]:
    out = []
    for c in disk(center, r):
        if c == center:
            continue
        feat = feature_map.get(c)
        if feat is None or not feat.placeable:
            continue
        out.append(c)
    return out


def build_city(coords: Coord, feature_map: FeatureMap,
               is_existing: bool = False) -> City:
    work_radius = 3
    placeable = _placeable_in_radius(coords, work_radius, feature_map)
    coastal = [c for c in placeable
               if feature_map[c].is_coastal]
    aq = _aqueduct_candidates_for(coords, feature_map)

    return City(
        coords=coords,
        coastal_flag=any(feature_map[c].is_coastal for c in placeable),
        aqueduct_candidates=aq,
        hansa_candidates=list(placeable),
        commhub_candidates=list(placeable),
        harbor_candidates=coastal,
        is_existing=is_existing,
    )


def enumerate_city_centers(
    feature_map: FeatureMap,
    existing_centers: List[Coord],
    min_spacing: int = 4,
) -> List[City]:
    """Tiles eligible to host a NEW city center.

    Filter rules: not water/mountain/wonder, distance ≥ min_spacing from every
    existing center.
    """
    candidates: List[City] = []
    for coords, feat in feature_map.items():
        if feat.is_water or feat.is_mountain or feat.is_wonder:
            continue
        # The center can sit on a tile that holds a resource or "other"
        # district visually, but not on top of one of the four optimised
        # district kinds. Civ 6 actually disallows centers on existing
        # districts — keep that strict.
        if feat.existing_district_kind is not None:
            continue
        if any(distance(coords, ec) < min_spacing for ec in existing_centers):
            continue
        candidates.append(build_city(coords, feature_map, is_existing=False))
    return candidates


def annotate_synergy(candidates: List[City], fixed_centers: List[Coord],
                     synergy_radius: int = 6) -> None:
    coords_pool = fixed_centers + [c.coords for c in candidates]
    for c in candidates:
        c.high_synergy = any(
            other != c.coords and distance(c.coords, other) <= synergy_radius
            for other in coords_pool
        )


# --- Phase 3: aqueduct enumeration -------------------------------------------

def aqueduct_enum(cluster: Cluster) -> Iterator[Dict[int, Optional[Coord]]]:
    """Yield every aqueduct assignment for the cluster.

    Each city contributes one of A_c ∪ {None}. None means "no aqueduct".
    """
    options: List[List[Optional[Coord]]] = []
    for c in cluster.cities:
        fixed_aq = c.fixed_assignment.aqueduct if c.fixed_assignment else None
        if _district_fixed(c, AQ):
            options.append([fixed_aq])
        else:
            options.append(list(c.aqueduct_candidates) + [None])
    for combo in product(*options):
        yield {i: combo[i] for i in range(len(cluster.cities))}


def aqueduct_enum_limited(
    cluster: Cluster,
    influence: Dict[Coord, int],
    budget_per_city: Optional[int] = None,
) -> Iterator[Dict[int, Optional[Coord]]]:
    """Yield aqueduct assignments after trimming each city's AQ options.

    The ranking is heuristic: prefer aqueduct tiles that sit next to the
    highest-influence Hansa candidate for that city. This preserves the
    obvious Hansa+Aqueduct triangles while keeping the combinatorics bounded.
    """
    if budget_per_city is None or budget_per_city <= 0:
        yield from aqueduct_enum(cluster)
        return

    options: List[List[Optional[Coord]]] = []
    for c in cluster.cities:
        fixed_aq = c.fixed_assignment.aqueduct if c.fixed_assignment else None
        if _district_fixed(c, AQ):
            options.append([fixed_aq])
            continue

        ranked = _rank_aqueduct_candidates(c, influence)
        trimmed = ranked[:budget_per_city]
        options.append(trimmed + [None])

    for combo in product(*options):
        yield {i: combo[i] for i in range(len(cluster.cities))}


def _rank_aqueduct_candidates(city: City, influence: Dict[Coord, int]) -> List[Coord]:
    hansa_candidates = set(city.hansa_candidates)

    def aq_key(aq: Coord) -> Tuple[int, int, Coord]:
        adjacent_hansas = [h for h in neighbours(aq) if h in hansa_candidates]
        best = max((influence.get(h, 0) for h in adjacent_hansas), default=-1)
        count = len(adjacent_hansas)
        return (-best, -count, aq)

    return sorted(city.aqueduct_candidates, key=aq_key)


# --- Phase 4: star centers ---------------------------------------------------

def _can_host_aq_for_any(coord: Coord, cluster: Cluster) -> bool:
    return any(coord in c.aqueduct_candidates for c in cluster.cities)


def rank_stars(
    cluster: Cluster,
    alpha: Dict[int, Optional[Coord]],
    feature_map: FeatureMap,
    influence: Dict[Coord, int],
) -> List[Tuple[Coord, float, int]]:
    """Identify star-candidate tiles T and rank by an upper bound on payoff.

    Returns list of (T, StarUB, k_T) sorted descending.
    """
    # For each tile T, count how many distinct cities could place a Hansa
    # adjacent to T (via H_c ∩ N(T)).
    eligible: Dict[Coord, Set[int]] = {}
    work_cities = [c for c in cluster.cities if not _district_fixed(c, H)]
    work_idx = {id(c): i for i, c in enumerate(cluster.cities)}

    # Pool of candidate centers T = union of all cluster cities' working radius.
    pool: Set[Coord] = set()
    for c in cluster.cities:
        # T can be ANY tile in N(H_c) — so the union of placeable + their neighbours.
        for h in c.hansa_candidates:
            pool.add(h)
            for n in neighbours(h):
                pool.add(n)
        if not _district_fixed(c, H):
            pool.add(c.coords)  # city center itself can host nothing useful
    # Drop water etc. — but T may itself be a placeable tile (CH at T) OR an
    # already-fixed district tile. We filter only "is on the map".
    pool = {p for p in pool if p in feature_map}

    for T in pool:
        for c in work_cities:
            ci = work_idx[id(c)]
            for h in c.hansa_candidates:
                if h == T:
                    continue
                if (h[0] - T[0], h[1] - T[1]) in _NEIGHBOUR_OFFSETS:
                    eligible.setdefault(T, set()).add(ci)
                    break
            else:
                continue

    ranked: List[Tuple[Coord, float, int]] = []
    for T, cities in eligible.items():
        k = len(cities)
        if k < 2:
            continue
        feat = feature_map.get(T)
        # Can a CommHub from one of the participating cities sit at T?
        ch_possible = (
            feat is not None
            and feat.placeable
            and any(T in cluster.cities[ci].commhub_candidates for ci in cities)
        )
        # Star upper bound (mathematical max contiguous chain).
        contiguous_hansa_gain = 4 * k - 2          # see Solution A §5.2
        ch_gold = k if ch_possible else 0
        if_center = influence.get(T, 0)
        if_neighbours = sum(influence.get(n, 0) for n in neighbours(T))
        ub = contiguous_hansa_gain + ch_gold + if_center + if_neighbours
        ranked.append((T, ub, k))

    ranked.sort(
        key=lambda x: (
            -x[1],                                # primary: UB desc
            -influence.get(x[0], 0),              # tie-break: IF(T)
            x[0],                                 # deterministic
        )
    )
    return ranked


# Local copy to avoid cyclic import with hex (the offsets live there but we
# want this module standalone-importable in tests).
_NEIGHBOUR_OFFSETS = {
    (2, 0), (-2, 0),
    (1, -1), (-1, -1),
    (1, 1), (-1, 1),
}
