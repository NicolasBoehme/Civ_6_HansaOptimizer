from dataclasses import dataclass
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .fallback import FallbackInfeasible, enumerate_aqueduct_tiles, enumerate_valid_centers, fallback_solve
from .fit import CityPlacement, Placement, StartingCity
from .hex import Coord, distance, tiles_within_radius
from .score import build_district_index, build_resource_index, score_hansa, score_total


@dataclass(frozen=True)
class GroupCandidate:
    size: int
    centers: Tuple[Coord, ...]
    placement: Placement
    name: str


def _in_bounds(board, coord: Coord) -> bool:
    col, row = coord
    rows, cols = board.tiles.shape
    return 0 <= row < rows and 0 <= col < cols


def _get_tile(board, coord: Coord):
    if not _in_bounds(board, coord):
        return None
    return board.tiles[coord[1], coord[0]]


def _is_blocked(tile) -> bool:
    return getattr(tile, "terrain", None) in {"ocean", "coast", "lake", "mountains", "wonder", "reef"}


def _is_open_tile(board, coord: Coord) -> bool:
    tile = _get_tile(board, coord)
    if tile is None or _is_blocked(tile):
        return False
    return getattr(getattr(tile, "contains", None), "kind", None) is None


def _occupied_starting_tiles(starting_city: StartingCity) -> Set[Coord]:
    occupied = {starting_city.center}
    for coord in (
        starting_city.hansa,
        starting_city.commhub,
        starting_city.harbor,
        starting_city.aqueduct,
    ):
        if coord is not None:
            occupied.add(coord)
    return occupied


def _placement_tiles(placement: Placement) -> Set[Coord]:
    return {
        coord
        for city in placement.cities
        for coord in (city.center, city.hansa, city.commhub, city.harbor, city.aqueduct)
        if coord is not None
    }


def _per_city_scores(board, placement: Placement, starting_city: StartingCity) -> List[int]:
    resource_index = build_resource_index(board)
    district_index = build_district_index(placement, starting_city, board)
    return [
        score_hansa(board, city.hansa, district_index, resource_index).total
        for city in placement.cities
    ]


def _placement_key(board, placement: Placement, starting_city: StartingCity) -> Tuple[int, int, float]:
    per_city = _per_city_scores(board, placement, starting_city)
    if not per_city:
        variance = 0.0
    else:
        mean = sum(per_city) / len(per_city)
        variance = sum((score - mean) ** 2 for score in per_city) / len(per_city)
    inward_aqueducts = sum(
        1
        for city in placement.cities
        if distance(city.center, city.aqueduct) == 1
    )
    return placement.score, inward_aqueducts, -variance


def _group_size_sequences(n: int) -> List[Tuple[int, ...]]:
    sequences: List[Tuple[int, ...]] = []

    def _walk(remaining: int, current: List[int]) -> None:
        if remaining == 0:
            sequences.append(tuple(current))
            return
        for size in (3, 2, 1):
            if size <= remaining:
                current.append(size)
                _walk(remaining - size, current)
                current.pop()

    _walk(n, [])
    sequences.sort(
        key=lambda seq: (
            seq.count(1),
            -seq.count(3),
            len(seq),
            tuple(-size for size in seq),
        )
    )
    return sequences


def _triangle_center_groups(centers: Sequence[Coord]) -> List[Tuple[Coord, Coord, Coord]]:
    groups: List[Tuple[Coord, Coord, Coord]] = []
    for combo in combinations(centers, 3):
        if (
            distance(combo[0], combo[1]) == 4
            and distance(combo[0], combo[2]) == 4
            and distance(combo[1], combo[2]) == 4
        ):
            groups.append(tuple(sorted(combo)))
    return groups


def _double_center_groups(centers: Sequence[Coord]) -> List[Tuple[Coord, Coord]]:
    groups: List[Tuple[Coord, Coord]] = []
    for combo in combinations(centers, 2):
        if distance(combo[0], combo[1]) == 4:
            groups.append(tuple(sorted(combo)))
    return groups


def _working_tiles(board, center: Coord, blocked: Set[Coord]) -> List[Coord]:
    return [
        coord
        for coord in tiles_within_radius(center, 3)
        if coord != center and coord not in blocked and _is_open_tile(board, coord)
    ]


def _preferred_aqueducts(
    board,
    center: Coord,
    centers: Sequence[Coord],
    blocked: Set[Coord],
) -> List[Coord]:
    candidates = [
        coord
        for coord in enumerate_aqueduct_tiles(board, center)
        if coord not in blocked
    ]
    if not candidates:
        return []
    best_distance = min(
        sum(distance(coord, other) for other in centers if other != center)
        for coord in candidates
    )
    return [
        coord
        for coord in candidates
        if sum(distance(coord, other) for other in centers if other != center) == best_distance
    ]


def _commhub_candidates(
    board,
    center: Coord,
    hansa: Coord,
    blocked: Set[Coord],
) -> List[Coord]:
    return [
        coord
        for coord in _working_tiles(board, center, blocked)
        if distance(coord, hansa) == 1
    ]


def _harbor_candidates(
    board,
    center: Coord,
    blocked: Set[Coord],
    hansas: Sequence[Coord],
) -> List[Coord]:
    candidates: List[Coord] = []
    for coord in _working_tiles(board, center, blocked):
        tile = _get_tile(board, coord)
        if tile is None:
            continue
        if getattr(tile, "terrain", None) == "coast":
            coastal = True
        else:
            coastal = any(
                (_get_tile(board, neighbour) is not None)
                and getattr(_get_tile(board, neighbour), "terrain", None) in {"coast", "ocean", "lake"}
                for neighbour in tiles_within_radius(coord, 1)
                if distance(coord, neighbour) == 1
            )
        if not coastal:
            continue
        if any(distance(coord, hansa) == 1 for hansa in hansas):
            candidates.append(coord)
    return candidates


def _optimise_group(board, starting_city: StartingCity, centers: Sequence[Coord], name: str) -> Optional[Placement]:
    occupied_start = _occupied_starting_tiles(starting_city)
    center_set = set(centers)
    aq_options: List[List[Coord]] = []

    for center in centers:
        options = _preferred_aqueducts(board, center, centers, occupied_start | center_set)
        if not options:
            return None
        aq_options.append(options)

    best: Optional[Placement] = None
    aq_choices: List[Optional[Coord]] = [None] * len(centers)

    def _search_hansas(index: int, used: Set[Coord]) -> None:
        nonlocal best

        hansa_options: List[List[Coord]] = []
        for center, aq in zip(centers, aq_choices):
            assert aq is not None
            candidates = [
                coord
                for coord in _working_tiles(board, center, occupied_start | center_set | used)
                if distance(coord, aq) == 1
            ]
            if not candidates:
                return
            hansa_options.append(candidates)

        hansa_order = sorted(range(len(centers)), key=lambda idx: len(hansa_options[idx]))
        hansas: List[Optional[Coord]] = [None] * len(centers)

        def _search_commhubs(order_index: int, used_now: Set[Coord]) -> None:
            commhub_options: List[List[Coord]] = []
            for center, hansa in zip(centers, hansas):
                assert hansa is not None
                candidates = _commhub_candidates(
                    board,
                    center,
                    hansa,
                    occupied_start | center_set | used_now,
                )
                if not candidates:
                    return
                commhub_options.append(candidates)

            commhub_order = sorted(range(len(centers)), key=lambda idx: len(commhub_options[idx]))
            commhubs: List[Optional[Coord]] = [None] * len(centers)

            def _search_harbors(hb_index: int, used_hb: Set[Coord]) -> None:
                nonlocal best
                if hb_index >= len(centers):
                    cities = tuple(
                        CityPlacement(
                            center=centers[city_index],
                            hansa=hansas[city_index],
                            commhub=commhubs[city_index],
                            harbor=harbors[city_index],
                            aqueduct=aq_choices[city_index],
                        )
                        for city_index in range(len(centers))
                    )
                    score = score_total(
                        board,
                        Placement(
                            cities=cities,
                            score=0,
                            template_name=name,
                            anchor=None,
                            rotation=None,
                            mirror=None,
                            instance=None,
                        ),
                        starting_city=starting_city,
                    )
                    placement = Placement(
                        cities=cities,
                        score=score,
                        template_name=name,
                        anchor=None,
                        rotation=None,
                        mirror=None,
                        instance=None,
                    )
                    if best is None or _placement_key(board, placement, starting_city) > _placement_key(board, best, starting_city):
                        best = placement
                    return

                city_index = hb_order[hb_index]
                options = [None] + harbor_options[city_index]
                for harbor in options:
                    if harbor is not None and harbor in used_hb:
                        continue
                    harbors[city_index] = harbor
                    next_used = used_hb | ({harbor} if harbor is not None else set())
                    _search_harbors(hb_index + 1, next_used)
                    harbors[city_index] = None

            def _search_commhub_tiles(commhub_index: int, used_ch: Set[Coord]) -> None:
                if commhub_index >= len(centers):
                    all_hansas = [coord for coord in hansas if coord is not None]
                    harbor_options.clear()
                    for city_index, center in enumerate(centers):
                        harbor_options.append(
                            _harbor_candidates(
                                board,
                                center,
                                occupied_start | center_set | used_ch,
                                all_hansas,
                            )
                        )
                    _search_harbors(0, used_ch)
                    return

                city_index = commhub_order[commhub_index]
                for commhub in commhub_options[city_index]:
                    if commhub in used_ch:
                        continue
                    commhubs[city_index] = commhub
                    _search_commhub_tiles(commhub_index + 1, used_ch | {commhub})
                    commhubs[city_index] = None

            harbor_options: List[List[Coord]] = []
            hb_order = list(range(len(centers)))
            harbors: List[Optional[Coord]] = [None] * len(centers)
            _search_commhub_tiles(0, set(used_now))

        def _search_hansa_tiles(h_index: int, used_h: Set[Coord]) -> None:
            if h_index >= len(centers):
                _search_commhubs(0, set(used_h))
                return

            city_index = hansa_order[h_index]
            for hansa in hansa_options[city_index]:
                if hansa in used_h:
                    continue
                hansas[city_index] = hansa
                _search_hansa_tiles(h_index + 1, used_h | {hansa})
                hansas[city_index] = None

        _search_hansa_tiles(0, set(used))

    def _search_aqueducts(aq_index: int, used: Set[Coord]) -> None:
        if aq_index >= len(centers):
            _search_hansas(0, set(used))
            return

        for aqueduct in aq_options[aq_index]:
            if aqueduct in used:
                continue
            aq_choices[aq_index] = aqueduct
            _search_aqueducts(aq_index + 1, used | {aqueduct})
            aq_choices[aq_index] = None

    _search_aqueducts(0, set())
    return best


def _build_group_candidates(board, starting_city: StartingCity, size: int) -> List[GroupCandidate]:
    if size not in (2, 3):
        return []

    valid_centers = enumerate_valid_centers(board, starting_city, [])
    center_groups: Iterable[Tuple[Coord, ...]]
    if size == 3:
        center_groups = _triangle_center_groups(valid_centers)
        name = "triangle_3"
    else:
        center_groups = _double_center_groups(valid_centers)
        name = "double_2"

    groups: List[GroupCandidate] = []
    for centers in center_groups:
        placement = _optimise_group(board, starting_city, centers, name)
        if placement is None:
            continue
        groups.append(
            GroupCandidate(
                size=size,
                centers=tuple(centers),
                placement=placement,
                name=name,
            )
        )
    return groups


def _centers_conflict(left: Sequence[Coord], right: Sequence[Coord]) -> bool:
    for left_center in left:
        for right_center in right:
            if distance(left_center, right_center) < 4:
                return True
    return False


def _candidate_conflicts(
    left: GroupCandidate,
    right: GroupCandidate,
) -> bool:
    if _centers_conflict(left.centers, right.centers):
        return True
    return bool(_placement_tiles(left.placement) & _placement_tiles(right.placement))


def _combine_placements(
    board,
    starting_city: StartingCity,
    selected: Sequence[GroupCandidate],
    singles: int,
) -> Optional[Placement]:
    prefilled = [city for candidate in selected for city in candidate.placement.cities]
    if singles:
        try:
            extended = fallback_solve(board, starting_city, singles, prefilled=prefilled)
        except FallbackInfeasible:
            return None
        cities = extended.cities
        name = "+".join([candidate.name for candidate in selected] + ["fallback"])
    else:
        cities = tuple(prefilled)
        name = "+".join(candidate.name for candidate in selected) if selected else None

    return Placement(
        cities=tuple(cities),
        score=score_total(
            board,
            Placement(
                cities=tuple(cities),
                score=0,
                template_name=name,
                anchor=None,
                rotation=None,
                mirror=None,
                instance=None,
            ),
            starting_city=starting_city,
        ),
        template_name=name,
        anchor=None,
        rotation=None,
        mirror=None,
        instance=None,
    )


def fit_preferred_patterns(board, starting_city, n: int) -> Optional[Placement]:
    sc = StartingCity.from_dict(starting_city, board)
    sequences = _group_size_sequences(n)
    cache: Dict[int, List[GroupCandidate]] = {}

    for sequence in sequences:
        group_sizes = [size for size in sequence if size in (2, 3)]
        singles = sequence.count(1)
        if any(size not in cache for size in group_sizes):
            for size in set(group_sizes):
                cache.setdefault(size, _build_group_candidates(board, sc, size))

        best: Optional[Placement] = None
        selected: List[GroupCandidate] = []

        def _search(index: int) -> None:
            nonlocal best
            if index >= len(group_sizes):
                placement = _combine_placements(board, sc, selected, singles)
                if placement is None:
                    return
                if best is None or _placement_key(board, placement, sc) > _placement_key(board, best, sc):
                    best = placement
                return

            size = group_sizes[index]
            for candidate in cache.get(size, []):
                if any(_candidate_conflicts(candidate, other) for other in selected):
                    continue
                selected.append(candidate)
                _search(index + 1)
                selected.pop()

        _search(0)
        if best is not None:
            return best

    return None
