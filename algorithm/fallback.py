from typing import Dict, List, Optional, Set, Tuple

from .fit import CityPlacement, Placement, StartingCity
from .hex import Coord, distance, neighbours, tiles_within_radius
from .score import (
    AQ,
    CH,
    OTHER,
    build_district_index,
    build_resource_index,
    score_hansa,
    score_total,
)


class FallbackInfeasible(RuntimeError):
    pass


def _in_bounds(board, coord: Coord) -> bool:
    col, row = coord
    rows, cols = board.tiles.shape
    return 0 <= row < rows and 0 <= col < cols


def _get_tile(board, coord: Coord):
    if not _in_bounds(board, coord):
        return None
    return board.tiles[coord[1], coord[0]]


def _iter_board_coords(board):
    rows, cols = board.tiles.shape
    for row in range(rows):
        for col in range(cols):
            if board.tiles[row, col] is not None:
                yield col, row


def _is_blocked(tile) -> bool:
    return getattr(tile, "terrain", None) in {"ocean", "coast", "lake", "mountains", "wonder", "reef"}


def _river_endpoint_coords(board) -> Set[Coord]:
    lookup = {}
    rows, cols = board.tiles.shape
    for row in range(rows):
        for col in range(cols):
            tile = board.tiles[row, col]
            if tile is not None:
                lookup[id(tile)] = (col, row)

    coords: Set[Coord] = set()
    for river in getattr(board, "rivers", ()) or ():
        left, right = river.getTiles()
        left_coord = lookup.get(id(left))
        right_coord = lookup.get(id(right))
        if left_coord is not None:
            coords.add(left_coord)
        if right_coord is not None:
            coords.add(right_coord)
    return coords


def _is_open_tile(board, coord: Coord) -> bool:
    tile = _get_tile(board, coord)
    if tile is None or _is_blocked(tile):
        return False
    return getattr(getattr(tile, "contains", None), "kind", None) is None


def _occupied_tiles(starting_city: StartingCity, placed: List[CityPlacement]) -> Set[Coord]:
    occupied = {starting_city.center}
    for coord in (
        starting_city.hansa,
        starting_city.commhub,
        starting_city.harbor,
        starting_city.aqueduct,
    ):
        if coord is not None:
            occupied.add(coord)
    for city in placed:
        occupied.update(
            coord
            for coord in (city.center, city.hansa, city.commhub, city.harbor, city.aqueduct)
            if coord is not None
        )
    return occupied


def compute_influence_field(board, starting_city) -> Dict[Coord, int]:
    sc = StartingCity.from_dict(starting_city, board)
    empty = Placement(
        cities=(),
        score=0,
        template_name=None,
        anchor=None,
        rotation=None,
        mirror=None,
        instance=None,
    )
    district_index = build_district_index(empty, sc, board)
    resource_index = build_resource_index(board)
    influence: Dict[Coord, int] = {}
    for coord in _iter_board_coords(board):
        influence[coord] = score_hansa(board, coord, district_index, resource_index).total
    return influence


def enumerate_valid_centers(board, starting_city, already_placed) -> List[Coord]:
    sc = StartingCity.from_dict(starting_city, board)
    centers = [city.center for city in already_placed]
    valid: List[Coord] = []
    for coord in _iter_board_coords(board):
        tile = _get_tile(board, coord)
        if tile is None or _is_blocked(tile):
            continue
        if getattr(getattr(tile, "contains", None), "kind", None) is not None:
            continue
        if distance(coord, sc.center) < 4:
            continue
        if any(distance(coord, center) < 4 for center in centers):
            continue
        valid.append(coord)
    return valid


def enumerate_aqueduct_tiles(board, center) -> List[Coord]:
    river_endpoints = _river_endpoint_coords(board)
    tiles: List[Coord] = []
    for coord in neighbours(center):
        tile = _get_tile(board, coord)
        if tile is None or not _is_open_tile(board, coord):
            continue
        if coord in river_endpoints:
            tiles.append(coord)
            continue
        if any(
            (neighbour in river_endpoints)
            or (
                (_get_tile(board, neighbour) is not None)
                and getattr(_get_tile(board, neighbour), "terrain", None) in {"lake", "mountains"}
            )
            for neighbour in neighbours(coord)
        ):
            tiles.append(coord)
    return tiles


def _fixed_board_district_index(board) -> Dict[Coord, str]:
    district_index: Dict[Coord, str] = {}
    for coord in _iter_board_coords(board):
        tile = _get_tile(board, coord)
        kind = getattr(getattr(tile, "contains", None), "kind", None)
        if kind is not None:
            district_index[coord] = kind
    return district_index


def find_district_triangle(board, center, taken) -> Optional[Tuple[Coord, Coord, Coord]]:
    resource_index = build_resource_index(board)
    fixed_districts = _fixed_board_district_index(board)
    best: Optional[Tuple[int, Tuple[Coord, Coord, Coord]]] = None
    candidates = [
        coord
        for coord in tiles_within_radius(center, 3)
        if coord not in taken and coord != center and _is_open_tile(board, coord)
    ]

    for aq in enumerate_aqueduct_tiles(board, center):
        if aq in taken:
            continue
        for hansa in candidates:
            if hansa == aq or distance(hansa, aq) != 1:
                continue
            for commhub in candidates:
                if commhub in {aq, hansa}:
                    continue
                if distance(commhub, hansa) != 1:
                    continue
                district_index = dict(fixed_districts)
                district_index[center] = OTHER
                district_index[commhub] = CH
                district_index[aq] = AQ
                score = score_hansa(board, hansa, district_index, resource_index).total
                if best is None or score > best[0]:
                    best = (score, (hansa, commhub, aq))
    return None if best is None else best[1]


def fallback_solve(board, starting_city, n, *, prefilled: Optional[List[CityPlacement]] = None) -> Placement:
    sc = StartingCity.from_dict(starting_city, board)
    influence = compute_influence_field(board, sc)
    placed: List[CityPlacement] = list(prefilled) if prefilled else []

    for _index in range(n):
        best_candidate: Optional[Tuple[int, CityPlacement]] = None
        occupied = _occupied_tiles(sc, placed)
        centers = sorted(
            enumerate_valid_centers(board, sc, placed),
            key=lambda coord: influence.get(coord, 0),
            reverse=True,
        )

        for center in centers:
            if center in occupied:
                continue
            triangle = find_district_triangle(board, center, occupied | {center})
            if triangle is None:
                continue
            hansa, commhub, aqueduct = triangle
            city = CityPlacement(
                center=center,
                hansa=hansa,
                commhub=commhub,
                harbor=None,
                aqueduct=aqueduct,
            )
            placement = Placement(
                cities=tuple(placed + [city]),
                score=0,
                template_name=None,
                anchor=None,
                rotation=None,
                mirror=None,
                instance=None,
            )
            score = score_total(board, placement, starting_city=sc)
            if best_candidate is None or score > best_candidate[0]:
                best_candidate = (score, city)

        if best_candidate is None:
            raise FallbackInfeasible("fallback could not place another city")
        placed.append(best_candidate[1])

    final = Placement(
        cities=tuple(placed),
        score=0,
        template_name=None,
        anchor=None,
        rotation=None,
        mirror=None,
        instance=None,
    )
    return Placement(
        cities=final.cities,
        score=score_total(board, final, starting_city=sc),
        template_name=None,
        anchor=None,
        rotation=None,
        mirror=None,
        instance=None,
    )
