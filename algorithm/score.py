from dataclasses import dataclass
from typing import Dict, Iterable, Literal, Optional

from .hex import Coord, neighbours


H = "hansa"
CH = "commhub"
HB = "harbor"
AQ = "aqueduct"
OTHER = "other"
DistrictKind = Literal["hansa", "commhub", "harbor", "aqueduct", "other"]
ResourceTier = Literal["bonus", "luxury", "strategic"]


@dataclass(frozen=True)
class HansaScoreBreakdown:
    commhub: int = 0
    harbor: int = 0
    aqueduct: int = 0
    other: int = 0
    luxury: int = 0
    bonus: int = 0

    @property
    def total(self) -> int:
        return (
            self.commhub
            + self.harbor
            + self.aqueduct
            + self.other
            + self.luxury
            + self.bonus
        )


def _in_bounds(board, coord: Coord) -> bool:
    col, row = coord
    rows, cols = board.tiles.shape
    return 0 <= row < rows and 0 <= col < cols


def _get_tile(board, coord: Coord):
    if not _in_bounds(board, coord):
        return None
    return board.tiles[coord[1], coord[0]]


def _iter_board_coords(board) -> Iterable[Coord]:
    rows, cols = board.tiles.shape
    for row in range(rows):
        for col in range(cols):
            if board.tiles[row, col] is not None:
                yield col, row


def _kind_from_tile(tile) -> Optional[DistrictKind]:
    contains = getattr(tile, "contains", None)
    kind = getattr(contains, "kind", None)
    if kind in (H, CH, HB, AQ, OTHER):
        return kind
    return None


def _coerce_starting_city(starting_city):
    if starting_city is None:
        return None
    if isinstance(starting_city, dict):
        return starting_city
    return {
        "center": starting_city.center,
        "hansa": starting_city.hansa,
        "commhub": starting_city.commhub,
        "harbor": starting_city.harbor,
        "aqueduct": starting_city.aqueduct,
    }


def build_district_index(placement, starting_city, board=None) -> Dict[Coord, DistrictKind]:
    district_index: Dict[Coord, DistrictKind] = {}

    if board is not None:
        for coord in _iter_board_coords(board):
            tile = _get_tile(board, coord)
            if tile is None:
                continue
            kind = _kind_from_tile(tile)
            if kind is not None:
                district_index[coord] = kind

    sc = _coerce_starting_city(starting_city)
    if sc is not None:
        center = sc.get("center")
        if center is not None:
            district_index[center] = OTHER
        for coord, kind in (
            (sc.get("hansa"), H),
            (sc.get("commhub"), CH),
            (sc.get("harbor"), HB),
            (sc.get("aqueduct"), AQ),
        ):
            if coord is not None:
                district_index[coord] = kind

    for city in getattr(placement, "cities", ()):
        district_index[city.center] = OTHER
        district_index[city.hansa] = H
        district_index[city.commhub] = CH
        district_index[city.aqueduct] = AQ
        if city.harbor is not None:
            district_index[city.harbor] = HB

    return district_index


def build_resource_index(board) -> Dict[Coord, ResourceTier]:
    resource_index: Dict[Coord, ResourceTier] = {}
    for coord in _iter_board_coords(board):
        tile = _get_tile(board, coord)
        contains = getattr(tile, "contains", None)
        tier = getattr(contains, "tier", None)
        if tier in ("bonus", "luxury", "strategic"):
            resource_index[coord] = tier
    return resource_index


def score_hansa(board, hansa_coord, district_index, resource_index) -> HansaScoreBreakdown:
    commhub = 0
    harbor = 0
    aqueduct = 0
    other = 0
    luxury = 0
    bonus = 0

    for coord in neighbours(hansa_coord):
        tile = _get_tile(board, coord)
        if tile is None:
            continue

        district_kind = district_index.get(coord)
        if district_kind == CH:
            commhub += 2
        elif district_kind == HB:
            harbor += 2
        elif district_kind == AQ:
            aqueduct += 2
        elif district_kind is not None:
            other += 1

        resource_tier = resource_index.get(coord)
        if resource_tier == "bonus":
            bonus += 1
        elif resource_tier in ("luxury", "strategic"):
            luxury += 2

    return HansaScoreBreakdown(
        commhub=commhub,
        harbor=harbor,
        aqueduct=aqueduct,
        other=other,
        luxury=luxury,
        bonus=bonus,
    )


def score_total(board, placement, *, resource_index=None, starting_city=None) -> int:
    resources = resource_index if resource_index is not None else build_resource_index(board)
    districts = build_district_index(placement, starting_city, board)
    total = 0
    for city in getattr(placement, "cities", ()):
        total += score_hansa(board, city.hansa, districts, resources).total
    return total
