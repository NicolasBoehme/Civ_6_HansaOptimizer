"""Phase 5 — greedy initialisation and branch-and-bound per (cluster, α, T*).

The branch order is: Hansas → CommHubs → Harbors. Aqueducts are fixed by α.
Within each level we visit free candidate tiles in descending marginal value.
"""
import copy
import math
from typing import Dict, List, Optional, Set, Tuple

from .features import FeatureMap
from .hex import Coord, neighbours
from .model import AQ, CH, H, HANSA_ONLY, HB, Assignment, City, Cluster, Score
from .scoring import (score_assignment, score_ch_at, score_hansa_at,
                      score_hb_at)


Decision = Tuple[int, str]   # (city_index, kind)


def objective(score: Score, mode: str, w: float) -> float:
    if mode == HANSA_ONLY:
        return float(score.production)
    return float(score.production) + w * float(score.gold)


def _district_fixed(city: City, kind: str) -> bool:
    if city.fixed_assignment is None:
        return False
    value = _get_field(city.fixed_assignment, kind)
    if value is not None:
        return True
    # Fully-existing cities treat missing entries as explicitly absent.
    return city.is_existing


def _candidate_set(city: City, kind: str,
                   star: Optional[Coord]) -> List[Coord]:
    if kind == H:
        base = list(city.hansa_candidates)
        if star is not None:
            star_neighs = set(neighbours(star))
            star_neighs.add(star)
            restricted = [t for t in base if t in star_neighs]
            # Star membership is opportunistic — if we have any neighbour-of-T*
            # candidate, prefer them; otherwise fall through to all candidates
            # (the city is non-participating).
            return restricted if restricted else base
        return base
    if kind == CH:
        return list(city.commhub_candidates)
    if kind == HB:
        return list(city.harbor_candidates)
    return []


def _initial_assignments(cluster: Cluster,
                         alpha: Dict[int, Optional[Coord]]
                         ) -> Tuple[Dict[int, Assignment], Set[Coord]]:
    out: Dict[int, Assignment] = {}
    used: Set[Coord] = set()
    for ci, city in enumerate(cluster.cities):
        a = Assignment()
        if city.fixed_assignment is not None:
            a = copy.deepcopy(city.fixed_assignment)
        if not _district_fixed(city, AQ):
            a.aqueduct = alpha.get(ci)
        out[ci] = a
        for t in (a.hansa, a.commhub, a.harbor, a.aqueduct):
            if t is not None:
                used.add(t)
    return out, used


def _build_decisions(cluster: Cluster) -> List[Decision]:
    """Hansa for every working city, then CommHub, then Harbor (coastal only)."""
    decisions: List[Decision] = []
    indexed = list(enumerate(cluster.cities))
    decisions.extend((i, H) for i, c in indexed if not _district_fixed(c, H))
    decisions.extend((i, CH) for i, c in indexed if not _district_fixed(c, CH))
    decisions.extend((i, HB) for i, c in indexed
                     if c.coastal_flag and not _district_fixed(c, HB))
    return decisions


def _set_field(a: Assignment, kind: str, value: Optional[Coord]) -> None:
    if kind == H:
        a.hansa = value
    elif kind == CH:
        a.commhub = value
    elif kind == HB:
        a.harbor = value
    elif kind == AQ:
        a.aqueduct = value


def _get_field(a: Assignment, kind: str) -> Optional[Coord]:
    if kind == H:
        return a.hansa
    if kind == CH:
        return a.commhub
    if kind == HB:
        return a.harbor
    return a.aqueduct


def _build_owners(assignments: Dict[int, Assignment]) -> Dict[Coord, Tuple[int, str]]:
    owners: Dict[Coord, Tuple[int, str]] = {}
    for ci, a in assignments.items():
        for kind, t in ((H, a.hansa), (CH, a.commhub),
                        (HB, a.harbor), (AQ, a.aqueduct)):
            if t is not None:
                owners[t] = (ci, kind)
    return owners


def _residual_ub(
    decisions: List[Decision],
    idx: int,
    assignments: Dict[int, Assignment],
    used: Set[Coord],
    cluster: Cluster,
    feature_map: FeatureMap,
    star: Optional[Coord],
    mode: str,
    w: float,
) -> float:
    """Admissible upper bound on the objective contribution of decisions[idx:].

    For each unplaced district, take the max marginal value over its free
    candidate tiles, with a future-bonus term capped by the number of OTHER
    unplaced districts (each can occupy at most one free neighbour tile).
    """
    owners = _build_owners(assignments)
    remaining = decisions[idx:]
    # Slots that could later land on a free neighbour of any unplaced tile.
    # An unplaced district from a different city is a slot; same-city districts
    # also count (own CH adj to own H, etc.).
    total_slots_after = max(0, len(remaining) - 1)
    ub = 0.0
    for (ci, kind) in remaining:
        city = cluster.cities[ci]
        cands = [t for t in _candidate_set(city, kind, star) if t not in used]
        if not cands:
            if kind == HB:
                continue          # harbour is optional
            return -math.inf      # infeasible — caller will skip branch
        best = 0.0
        for t in cands:
            free_neighs = sum(
                1 for n in neighbours(t)
                if n not in used and n in feature_map and feature_map[n].placeable
            )
            future_cap = min(free_neighs, total_slots_after)
            if kind == H:
                s = score_hansa_at(t, feature_map, owners) + 2 * future_cap
                contrib = s
            elif kind == CH:
                s = score_ch_at(t, feature_map, owners) + future_cap
                contrib = w * s
            else:  # HB
                s = score_hb_at(t, feature_map, owners) + future_cap
                contrib = w * s
            if contrib > best:
                best = contrib
        ub += best
    return ub


def greedy_init(
    cluster: Cluster,
    alpha: Dict[int, Optional[Coord]],
    star: Optional[Coord],
    feature_map: FeatureMap,
    influence: Dict[Coord, int],
    mode: str,
    w: float,
) -> Tuple[Dict[int, Assignment], Score]:
    assignments, used = _initial_assignments(cluster, alpha)

    work_cities = list(enumerate(cluster.cities))

    # Hansa pass: star-participating cities first (they take N(T*) ∩ H_c),
    # then non-participating greedy by IF + own-aqueduct adjacency.
    if star is not None:
        star_ring = set(neighbours(star)) | {star}
        for ci, city in work_cities:
            if _district_fixed(city, H):
                continue
            cands = [t for t in city.hansa_candidates
                     if t in star_ring and t not in used]
            if not cands:
                continue
            owners = _build_owners(assignments)
            best_t = max(cands, key=lambda t: score_hansa_at(t, feature_map, owners))
            assignments[ci].hansa = best_t
            used.add(best_t)

    for ci, city in work_cities:
        if _district_fixed(city, H) or assignments[ci].hansa is not None:
            continue
        cands = [t for t in city.hansa_candidates if t not in used]
        if not cands:
            continue
        own_aq = assignments[ci].aqueduct
        owners = _build_owners(assignments)

        def hansa_key(t):
            base = score_hansa_at(t, feature_map, owners) + influence.get(t, 0)
            if own_aq is not None and (own_aq[0] - t[0], own_aq[1] - t[1]) in {
                (2, 0), (-2, 0), (1, -1), (-1, -1), (1, 1), (-1, 1)
            }:
                base += 2
            return base

        best_t = max(cands, key=hansa_key)
        assignments[ci].hansa = best_t
        used.add(best_t)

    # CommHub pass — adjacent to own Hansa if possible, else best by river bonus.
    for ci, city in work_cities:
        if _district_fixed(city, CH):
            continue
        cands = [t for t in city.commhub_candidates if t not in used]
        if not cands:
            continue
        owners = _build_owners(assignments)
        own_h = assignments[ci].hansa
        adj_to_h = []
        if own_h is not None:
            adj_to_h = [t for t in cands
                        if (t[0] - own_h[0], t[1] - own_h[1]) in {
                            (2, 0), (-2, 0), (1, -1), (-1, -1), (1, 1), (-1, 1)
                        }]
        pool = adj_to_h if adj_to_h else cands
        best_t = max(pool, key=lambda t: score_ch_at(t, feature_map, owners))
        assignments[ci].commhub = best_t
        used.add(best_t)

    # Harbor pass for coastal cities.
    for ci, city in work_cities:
        if not city.coastal_flag or _district_fixed(city, HB):
            continue
        cands = [t for t in city.harbor_candidates if t not in used]
        if not cands:
            continue
        owners = _build_owners(assignments)
        best_t = max(cands, key=lambda t: score_hb_at(t, feature_map, owners))
        # Only place if it actually adds value (or always — harbor is optional).
        if score_hb_at(best_t, feature_map, owners) > 0:
            assignments[ci].harbor = best_t
            used.add(best_t)

    return assignments, score_assignment(cluster.cities, assignments, feature_map)


def branch_and_bound(
    cluster: Cluster,
    alpha: Dict[int, Optional[Coord]],
    star: Optional[Coord],
    feature_map: FeatureMap,
    influence: Dict[Coord, int],
    lower_bound: Optional[Tuple[Dict[int, Assignment], Score]],
    mode: str,
    w: float,
    node_budget: int = 1_000,
) -> Tuple[Dict[int, Assignment], Score]:
    decisions = _build_decisions(cluster)
    assignments, used = _initial_assignments(cluster, alpha)

    # Initialise best from greedy lower bound or the bare partial.
    if lower_bound is None:
        best_assign, best_score = greedy_init(
            cluster, alpha, star, feature_map, influence, mode, w
        )
    else:
        best_assign, best_score = lower_bound
    best_obj = objective(best_score, mode, w)

    state = {"nodes": 0}

    def recurse(idx: int) -> None:
        if state["nodes"] >= node_budget:
            return
        state["nodes"] += 1
        if idx == len(decisions):
            score = score_assignment(cluster.cities, assignments, feature_map)
            obj = objective(score, mode, w)
            nonlocal_set(obj, score)
            return

        ci, kind = decisions[idx]
        city = cluster.cities[ci]
        cands = [t for t in _candidate_set(city, kind, star) if t not in used]
        # Always consider "skip" for harbour (it's optional).
        if kind == HB:
            cands = cands + [None]
        if not cands:
            # Mandatory district has no free candidate — infeasible branch.
            return

        # Order candidates by current marginal contribution descending.
        owners = _build_owners(assignments)
        if kind == H:
            cands.sort(
                key=lambda t: -(score_hansa_at(t, feature_map, owners) if t else 0)
            )
        elif kind == CH:
            cands.sort(
                key=lambda t: -(score_ch_at(t, feature_map, owners) if t else 0)
            )
        else:
            cands.sort(
                key=lambda t: -(score_hb_at(t, feature_map, owners) if t else 0)
            )

        for t in cands:
            _set_field(assignments[ci], kind, t)
            if t is not None:
                used.add(t)

            partial_score = score_assignment(cluster.cities, assignments, feature_map)
            partial_obj = objective(partial_score, mode, w)
            ub = _residual_ub(
                decisions, idx + 1, assignments, used, cluster,
                feature_map, star, mode, w,
            )
            if partial_obj + ub > best_obj + 1e-9:
                recurse(idx + 1)

            _set_field(assignments[ci], kind, None)
            if t is not None:
                used.discard(t)

            if state["nodes"] >= node_budget:
                return

    def nonlocal_set(obj: float, score: Score) -> None:
        nonlocal best_obj, best_score, best_assign
        if obj > best_obj + 1e-9:
            best_obj = obj
            best_score = score
            best_assign = copy.deepcopy(assignments)

    recurse(0)
    return best_assign, best_score
