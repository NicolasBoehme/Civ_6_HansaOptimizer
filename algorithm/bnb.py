"""Per-cluster solver.

Two nested loops:

1. **Aqueducts (outer).** Each city has at most 3-4 candidates; total
   `4^k ≤ 256` for k ≤ 4. We enumerate every legal aqueduct combination.

2. **Hansas (inner, branch-and-bound).** With aqueducts fixed, we recurse over
   cities placing one Hansa each, ordered by decreasing single-step delta and
   pruned by a tight admissible upper bound on the remaining cities.

Once both AQs and Hs are committed, the CommHub and Harbor for each city are
fixed by a deterministic greedy pass: each district's contribution is purely a
function of adjacencies and there is no cross-city contention in practice, so
picking the candidate with the best per-step objective is optimal at this
stage.

This shape replaces the previous star-pre-enumeration + general B&B, which
spent most of its time recomputing scores at high-fan-out interior nodes. The
new code finds the brute-force optimum on the n=2 plains test board (24 prod)
in ~10 ms vs ~12 s before.
"""
import copy
from itertools import product
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .features import FeatureMap
from .hex import Coord, neighbours
from .model import (AQ, CH, H, HANSA_ONLY, HB,
                    Assignment, City, Cluster, Score)
from .scoring import (HANSA_GAIN, resource_bonus, score_assignment,
                      score_ch_at, score_hansa_at, score_hb_at)

Owners = Dict[Coord, Tuple[int, str]]
Alpha = Dict[int, Optional[Coord]]

_NEIGHBOUR_OFFSETS = {
    (2, 0), (-2, 0),
    (1, -1), (-1, -1),
    (1, 1), (-1, 1),
}


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
    return city.is_existing


def _get_field(a: Assignment, kind: str) -> Optional[Coord]:
    if kind == H:
        return a.hansa
    if kind == CH:
        return a.commhub
    if kind == HB:
        return a.harbor
    return a.aqueduct


def _aqueduct_options(cluster: Cluster) -> List[List[Optional[Coord]]]:
    options: List[List[Optional[Coord]]] = []
    for c in cluster.cities:
        if _district_fixed(c, AQ):
            fixed_aq = c.fixed_assignment.aqueduct if c.fixed_assignment else None
            options.append([fixed_aq])
        else:
            opts: List[Optional[Coord]] = list(c.aqueduct_candidates)
            opts.append(None)
            options.append(opts)
    return options


def _enumerate_alphas(cluster: Cluster) -> Iterator[Alpha]:
    options = _aqueduct_options(cluster)
    for combo in product(*options):
        seen: Set[Coord] = set()
        clash = False
        for t in combo:
            if t is None:
                continue
            if t in seen:
                clash = True
                break
            seen.add(t)
        if clash:
            continue
        yield {i: combo[i] for i in range(len(cluster.cities))}


def _seed(cluster: Cluster, alpha: Alpha
          ) -> Optional[Tuple[Dict[int, Assignment], Owners, Set[Coord]]]:
    assignments: Dict[int, Assignment] = {}
    owners: Owners = {}
    used: Set[Coord] = set()
    for ci, city in enumerate(cluster.cities):
        a = (copy.deepcopy(city.fixed_assignment)
             if city.fixed_assignment is not None else Assignment())
        if not _district_fixed(city, AQ):
            a.aqueduct = alpha.get(ci)
        assignments[ci] = a
        for kind, t in ((H, a.hansa), (CH, a.commhub),
                        (HB, a.harbor), (AQ, a.aqueduct)):
            if t is None:
                continue
            if t in used:
                return None
            owners[t] = (ci, kind)
            used.add(t)
    return assignments, owners, used


def _hansa_delta(tile: Coord, owners: Owners,
                 feature_map: FeatureMap) -> int:
    """Production delta from placing a Hansa at `tile` given current owners.

    Includes both the new Hansa's own score (resources + adjacent districts)
    and the +1 each adjacent already-placed Hansa receives in turn.
    """
    delta = score_hansa_at(tile, feature_map, owners)
    for n in neighbours(tile):
        owned = owners.get(n)
        if owned is not None and owned[1] == H:
            delta += 1
    return delta


def _hansa_max_potential(tile: Coord, owners: Owners, used: Set[Coord],
                         feature_map: FeatureMap, slots_after: int) -> int:
    """Admissible upper bound on the production a Hansa at `tile` can ever
    contribute, given current owners and `slots_after` remaining placements
    that could land on this tile's empty placeable neighbours.
    """
    base = _hansa_delta(tile, owners, feature_map)
    free = 0
    for n in neighbours(tile):
        if n in used:
            continue
        feat = feature_map.get(n)
        if feat is None or not feat.placeable:
            continue
        free += 1
    return base + 2 * min(free, slots_after)


def _greedy_finish(cluster: Cluster,
                   assignments: Dict[int, Assignment],
                   owners: Owners,
                   used: Set[Coord],
                   feature_map: FeatureMap,
                   mode: str, w: float) -> Score:
    """With AQs and Hansas locked in, place CommHubs and Harbors greedily."""
    for ci, city in enumerate(cluster.cities):
        if _district_fixed(city, CH):
            continue
        cands = [t for t in city.commhub_candidates if t not in used]
        if not cands:
            continue
        best_t = cands[0]
        best_obj = float("-inf")
        for t in cands:
            assignments[ci].commhub = t
            owners[t] = (ci, CH)
            score = score_assignment(cluster.cities, assignments, feature_map)
            obj = objective(score, mode, w)
            del owners[t]
            if obj > best_obj:
                best_obj = obj
                best_t = t
        assignments[ci].commhub = best_t
        owners[best_t] = (ci, CH)
        used.add(best_t)

    for ci, city in enumerate(cluster.cities):
        if _district_fixed(city, HB) or not city.coastal_flag:
            continue
        cands = [t for t in city.harbor_candidates if t not in used]
        if not cands:
            continue
        baseline_obj = objective(
            score_assignment(cluster.cities, assignments, feature_map),
            mode, w,
        )
        best_t: Optional[Coord] = None
        best_obj = baseline_obj
        for t in cands:
            assignments[ci].harbor = t
            owners[t] = (ci, HB)
            score = score_assignment(cluster.cities, assignments, feature_map)
            obj = objective(score, mode, w)
            del owners[t]
            if obj > best_obj:
                best_obj = obj
                best_t = t
        assignments[ci].harbor = best_t
        if best_t is not None:
            owners[best_t] = (ci, HB)
            used.add(best_t)

    return score_assignment(cluster.cities, assignments, feature_map)


def _free_neighbour_count(tile: Coord, used: Set[Coord],
                          feature_map: FeatureMap) -> int:
    n = 0
    for nb in neighbours(tile):
        if nb in used:
            continue
        feat = feature_map.get(nb)
        if feat is None or not feat.placeable:
            continue
        n += 1
    return n


def _solve_for_alpha(cluster: Cluster, alpha: Alpha,
                     feature_map: FeatureMap, mode: str, w: float,
                     incumbent_obj: float
                     ) -> Optional[Tuple[Dict[int, Assignment], Score, float]]:
    """Recursive Hansa search with admissible UB pruning. CHs and HBs are
    filled greedily once Hansas are committed at each leaf.
    """
    seeded = _seed(cluster, alpha)
    if seeded is None:
        return None
    seed_assign, seed_owners, seed_used = seeded

    h_indices: List[int] = []
    h_lists: List[List[Coord]] = []
    for ci, city in enumerate(cluster.cities):
        if _district_fixed(city, H):
            continue
        cands = [t for t in city.hansa_candidates if t not in seed_used]
        if not cands:
            return None
        h_indices.append(ci)
        h_lists.append(cands)

    extra_slots = sum(
        (0 if _district_fixed(c, CH) else 1)
        + (1 if c.coastal_flag and not _district_fixed(c, HB) else 0)
        for c in cluster.cities
    )

    state = {
        "assign": seed_assign,
        "owners": dict(seed_owners),
        "used": set(seed_used),
        "placed_hs": [],              # tiles in placement order
        "best": None,                 # (assign_copy, score, obj)
        "best_obj": incumbent_obj,
    }

    # In combination mode each CH/HB also yields gold; the worst-case gold per
    # slot is bounded by 6 river adjacencies + 6 district adjacencies = 18,
    # then weighted by w. We use this as a slack term so the same bound covers
    # both modes admissibly.
    gold_slack_per_slot = 0.0 if mode == HANSA_ONLY else 18.0 * float(w)

    def recurse(level: int, partial_prod: int) -> None:
        if level == len(h_indices):
            local_assign = {ci: copy.deepcopy(a)
                            for ci, a in state["assign"].items()}
            local_owners = dict(state["owners"])
            local_used = set(state["used"])
            score = _greedy_finish(cluster, local_assign, local_owners,
                                   local_used, feature_map, mode, w)
            obj = objective(score, mode, w)
            if obj > state["best_obj"] + 1e-9:
                state["best_obj"] = obj
                state["best"] = (local_assign, score, obj)
            return

        ci = h_indices[level]
        cands = [t for t in h_lists[level] if t not in state["used"]]
        if not cands:
            return

        # Best-first: sort candidates by current single-step delta descending.
        scored: List[Tuple[int, Coord]] = []
        for t in cands:
            scored.append((_hansa_delta(t, state["owners"], feature_map), t))
        scored.sort(key=lambda x: -x[0])

        for delta, t in scored:
            new_prod = partial_prod + delta

            state["assign"][ci].hansa = t
            state["owners"][t] = (ci, H)
            state["used"].add(t)
            state["placed_hs"].append(t)

            # Admissible UB on remaining production / objective.
            #
            # Already-placed Hansas can each gain +2 per future CH/HB tile
            # that lands on one of their still-empty placeable neighbours.
            # The correct accounting is per-Hansa (not per-slot): a single
            # CH neighbouring two placed Hansas legitimately donates +2 to
            # each of them. Using per-slot would underestimate and prune
            # optimal branches.
            placed_residual = 0
            for h in state["placed_hs"]:
                free = _free_neighbour_count(h, state["used"], feature_map)
                placed_residual += 2 * min(free, extra_slots)

            # Each yet-to-place Hansa contributes at most its max-potential,
            # measured against the *current* owners + used set. The +1 cross-
            # Hansa term from future Hansa neighbours is absorbed into the
            # +2-per-slot future-cap term, which is loose but admissible.
            ub_rest = 0
            infeasible = False
            for fut_level in range(level + 1, len(h_indices)):
                fut_cands = [u for u in h_lists[fut_level]
                             if u not in state["used"]]
                if not fut_cands:
                    infeasible = True
                    break
                slots_after = (len(h_indices) - fut_level - 1) + extra_slots
                best_pot = max(
                    _hansa_max_potential(u, state["owners"], state["used"],
                                         feature_map, slots_after)
                    for u in fut_cands
                )
                ub_rest += best_pot

            if not infeasible:
                ub_total = (float(new_prod + placed_residual + ub_rest)
                            + extra_slots * gold_slack_per_slot)
                if ub_total > state["best_obj"] + 1e-9:
                    recurse(level + 1, new_prod)

            state["assign"][ci].hansa = None
            del state["owners"][t]
            state["used"].discard(t)
            state["placed_hs"].pop()

    recurse(0, 0)
    return state["best"]


def solve_cluster(cluster: Cluster, feature_map: FeatureMap,
                  mode: str, w: float
                  ) -> Tuple[Dict[int, Assignment], Score]:
    best_assign: Optional[Dict[int, Assignment]] = None
    best_score = Score()
    best_obj = float("-inf")

    for alpha in _enumerate_alphas(cluster):
        result = _solve_for_alpha(cluster, alpha, feature_map, mode, w, best_obj)
        if result is None:
            continue
        assign, score, obj = result
        if obj > best_obj + 1e-9:
            best_obj = obj
            best_assign = assign
            best_score = score

    if best_assign is None:
        empty = {i: Assignment() for i, _ in enumerate(cluster.cities)}
        return empty, Score()
    return best_assign, best_score
