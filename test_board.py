"""Built-in synthetic board for exercising the solver from main.py.

The board is a plains-only double-width hex grid. Three long river spines
intersect just north of the map center so the optimizer has a deterministic
cluster of river-adjacent tiles to work with.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


Coord = Tuple[int, int]

_NEIGHBOUR_OFFSETS = {
    (2, 0), (-2, 0),
    (1, -1), (-1, -1),
    (1, 1), (-1, 1),
}


@dataclass
class Tile:
    terrain: str
    contains: Optional[object] = None


@dataclass
class District:
    kind: str


class River:
    def __init__(self, tile1: Tile, tile2: Tile):
        self.tile1 = tile1
        self.tile2 = tile2

    def getTiles(self) -> Tuple[Tile, Tile]:
        return self.tile1, self.tile2


class Board:
    def __init__(
        self,
        tiles: np.ndarray,
        rivers: List[River],
        center: Coord,
        river_junction: Coord,
        starting_city_center: Coord,
    ):
        self.tiles = tiles
        self.rivers = rivers
        self.center = center
        self.river_junction = river_junction
        self.starting_city_center = starting_city_center


def _add(a: Coord, b: Coord) -> Coord:
    return a[0] + b[0], a[1] + b[1]


def _new_tiles(rows: int, cols: int, parity: int) -> Tuple[np.ndarray, Dict[Coord, Tile]]:
    tiles = np.empty((rows, cols), dtype=object)
    tiles.fill(None)
    coord_index: Dict[Coord, Tile] = {}
    for row in range(rows):
        for col in range(cols):
            if (col + row) % 2 != parity:
                continue
            tile = Tile("plains")
            tiles[row, col] = tile
            coord_index[(col, row)] = tile
    return tiles, coord_index


def _are_adjacent(a: Coord, b: Coord) -> bool:
    return (b[0] - a[0], b[1] - a[1]) in _NEIGHBOUR_OFFSETS


def _center_coord(rows: int, cols: int) -> Coord:
    return cols // 2, rows // 2


def _full_line(origin: Coord, backward: Coord, forward: Coord, coord_index: Dict[Coord, Tile]) -> List[Coord]:
    path = [origin]

    cursor = origin
    while True:
        candidate = _add(cursor, backward)
        if candidate not in coord_index:
            break
        path.insert(0, candidate)
        cursor = candidate

    cursor = origin
    while True:
        candidate = _add(cursor, forward)
        if candidate not in coord_index:
            break
        path.append(candidate)
        cursor = candidate

    return path


def _add_river_path(
    rivers: List[River],
    coord_index: Dict[Coord, Tile],
    path: Sequence[Coord],
    seen_segments: set[frozenset[Coord]],
) -> None:
    for left, right in zip(path, path[1:]):
        if left not in coord_index or right not in coord_index:
            raise ValueError(f"River path uses an invalid board coordinate: {left} -> {right}")
        if not _are_adjacent(left, right):
            raise ValueError(f"River segment is not adjacent: {left} -> {right}")

        segment = frozenset((left, right))
        if segment in seen_segments:
            continue
        seen_segments.add(segment)
        rivers.append(River(coord_index[left], coord_index[right]))


def build_three_river_plains_board(
    rows: int = 9,
    cols: int = 17,
) -> Tuple[Board, dict]:
    """Return a deterministic plains board with a starting city at the center."""
    if rows < 5 or cols < 9:
        raise ValueError("Synthetic test board must be at least 5 rows by 9 columns")

    center = _center_coord(rows, cols)
    parity = (center[0] + center[1]) % 2
    tiles, coord_index = _new_tiles(rows, cols, parity)

    if center not in coord_index:
        raise ValueError("Configured center is not a valid tile on this board")
    coord_index[center].contains = District("other")

    # In double-width hex coordinates there is no straight "north" tile.
    # This junction is the north-west tile immediately above the center.
    river_junction = (center[0] - 1, center[1] - 1)
    if river_junction not in coord_index:
        raise ValueError("Configured river junction is not a valid tile on this board")

    rivers: List[River] = []
    seen_segments: set[frozenset[Coord]] = set()

    _add_river_path(
        rivers,
        coord_index,
        _full_line(river_junction, (-2, 0), (2, 0), coord_index),
        seen_segments,
    )
    _add_river_path(
        rivers,
        coord_index,
        _full_line(river_junction, (-1, -1), (1, 1), coord_index),
        seen_segments,
    )
    _add_river_path(
        rivers,
        coord_index,
        _full_line(river_junction, (1, -1), (-1, 1), coord_index),
        seen_segments,
    )

    starting_city = {
        "center": center,
        "hansa": None,
        "commhub": None,
        "harbor": None,
        "aqueduct": None,
    }
    return (
        Board(
            tiles=tiles,
            rivers=rivers,
            center=center,
            river_junction=river_junction,
            starting_city_center=center,
        ),
        starting_city,
    )


def board_summary(board: Board) -> str:
    tile_count = sum(tile is not None for tile in board.tiles.flat)
    return (
        f"Built-in hypothetical plains board: {tile_count} tiles, "
        f"{len(board.rivers)} river segments, center={board.center}, "
        f"river_junction={board.river_junction}, "
        f"starting_city={board.starting_city_center}"
    )
