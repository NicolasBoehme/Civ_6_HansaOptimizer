"""Built-in Civ-like board for exercising the solver from main.py.

This is still a deterministic test map, but it is no longer a featureless
plains grid. The layout includes coasts, ocean, a lake, hills, mountains,
reefs, rivers, and a small spread of land and sea resources so the rendered
board reads more like an actual Civilization VI map.
"""
from collections import Counter
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


@dataclass
class Resource:
    name: str
    tier: str


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


def _set_terrain(coord_index: Dict[Coord, Tile], coord: Coord, terrain: str) -> None:
    tile = coord_index.get(coord)
    if tile is not None:
        tile.terrain = terrain
        if terrain in {"ocean", "coast", "lake", "reef", "wonder"}:
            if isinstance(tile.contains, District):
                raise ValueError(f"cannot turn occupied district tile into {terrain}: {coord}")


def _set_resource(
    coord_index: Dict[Coord, Tile],
    coord: Coord,
    name: str,
    tier: str,
) -> None:
    tile = coord_index.get(coord)
    if tile is not None and not isinstance(tile.contains, District):
        tile.contains = Resource(name=name, tier=tier)


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


def build_civ_like_test_board(
    rows: int = 13,
    cols: int = 25,
) -> Tuple[Board, dict]:
    """Return a deterministic hand-authored board that resembles a Civ 6 map."""
    if rows < 11 or cols < 21:
        raise ValueError("Civ-like test board must be at least 11 rows by 21 columns")

    center = _center_coord(rows, cols)
    parity = (center[0] + center[1]) % 2
    tiles, coord_index = _new_tiles(rows, cols, parity)

    start = (center[0] - 2, center[1])
    if start not in coord_index:
        raise ValueError("Configured starting city is not a valid tile on this board")
    coord_index[start].contains = District("other")

    river_junction = start

    west_coast = 4
    east_coast = cols - 5
    east_ocean = cols - 3
    for coord, tile in coord_index.items():
        col, _row = coord
        if col <= 2 or col >= east_ocean:
            tile.terrain = "ocean"
        elif col == west_coast or col == east_coast:
            tile.terrain = "coast"

    terrain_patches = {
        "coast": {
            (start[0] + 6, start[1] + 4),
            (start[0] + 7, start[1] + 3),
            (start[0] + 8, start[1] + 2),
            (start[0] + 9, start[1] + 1),
            (start[0] + 8, start[1] + 4),
            (start[0] + 7, start[1] + 5),
        },
        "ocean": {
            (start[0] + 10, start[1] + 2),
            (start[0] + 11, start[1] + 3),
            (start[0] + 12, start[1] + 4),
            (start[0] + 10, start[1] + 4),
            (start[0] + 11, start[1] + 5),
        },
        "lake": {
            (start[0], start[1] - 4),
        },
        "reef": {
            (east_coast + 1, center[1] - 1),
            (east_coast + 1, center[1] + 1),
        },
        "wonder": {
            (start[0] + 8, start[1] - 4),
        },
        "mountains": {
            (start[0] - 3, start[1] - 5),
            (start[0] - 4, start[1] - 4),
            (start[0] - 3, start[1] - 3),
            (start[0] + 3, start[1] - 3),
            (start[0] + 4, start[1] - 2),
            (start[0] + 6, start[1] - 2),
            (start[0] + 7, start[1] - 1),
            (start[0] + 5, start[1] + 3),
            (start[0] + 7, start[1] + 3),
        },
        "hills": {
            (start[0] - 5, start[1] - 3),
            (start[0] - 4, start[1] - 2),
            (start[0] - 3, start[1] - 1),
            (start[0] - 2, start[1]),
            (start[0] - 1, start[1] + 1),
            (start[0] + 1, start[1] - 1),
            (start[0] + 2, start[1]),
            (start[0] + 3, start[1] + 1),
            (start[0] + 5, start[1] - 1),
            (start[0] + 6, start[1]),
            (start[0] - 4, start[1] + 2),
            (start[0] - 2, start[1] + 2),
            (start[0], start[1] + 2),
            (start[0] + 2, start[1] + 2),
            (start[0] + 4, start[1] + 2),
            (start[0] + 6, start[1] + 2),
            (start[0] + 8, start[1]),
            (start[0] + 8, start[1] + 4),
        },
    }

    for terrain, coords in terrain_patches.items():
        for coord in coords:
            _set_terrain(coord_index, coord, terrain)

    rivers: List[River] = []
    seen_segments: set[frozenset[Coord]] = set()
    main_river = [
        (start[0] - 5, start[1] - 5),
        (start[0] - 4, start[1] - 4),
        (start[0] - 3, start[1] - 3),
        (start[0] - 2, start[1] - 2),
        (start[0] - 1, start[1] - 1),
        start,
        (start[0] + 1, start[1] + 1),
        (start[0] + 2, start[1] + 2),
        (start[0] + 3, start[1] + 3),
        (start[0] + 5, start[1] + 3),
        (start[0] + 7, start[1] + 3),
        (start[0] + 8, start[1] + 2),
        (start[0] + 9, start[1] + 1),
        (start[0] + 10, start[1] + 2),
    ]
    north_tributary = [
        (start[0] + 7, start[1] - 3),
        (start[0] + 5, start[1] - 3),
        (start[0] + 3, start[1] - 3),
        (start[0] + 2, start[1] - 2),
        (start[0] + 1, start[1] - 1),
        start,
    ]
    southwest_tributary = [
        (start[0] - 7, start[1] + 1),
        (start[0] - 5, start[1] + 1),
        (start[0] - 4, start[1]),
        (start[0] - 2, start[1]),
        start,
    ]
    river_paths = [main_river, north_tributary, southwest_tributary]
    for path in river_paths:
        _add_river_path(rivers, coord_index, path, seen_segments)

    resources = [
        ((start[0] - 2, start[1] + 2), "wheat", "bonus"),
        ((start[0] + 1, start[1] + 1), "cattle", "bonus"),
        ((start[0] + 2, start[1]), "iron", "strategic"),
        ((start[0] + 4, start[1]), "silk", "luxury"),
        ((start[0] + 6, start[1] + 2), "stone", "bonus"),
        ((east_coast, center[1]), "fish", "bonus"),
        ((east_coast, center[1] + 4), "pearls", "luxury"),
    ]
    for coord, name, tier in resources:
        _set_resource(coord_index, coord, name, tier)

    starting_city = {
        "center": start,
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
            starting_city_center=start,
        ),
        starting_city,
    )


def build_three_river_plains_board(
    rows: int = 9,
    cols: int = 17,
) -> Tuple[Board, dict]:
    """Compatibility alias for the old test-board entry point."""
    return build_civ_like_test_board(rows=max(rows, 13), cols=max(cols, 25))


def board_summary(board: Board) -> str:
    terrain_counts = Counter(
        tile.terrain
        for tile in board.tiles.flat
        if tile is not None
    )
    resource_count = sum(
        getattr(getattr(tile, "contains", None), "tier", None) is not None
        for tile in board.tiles.flat
        if tile is not None
    )
    tile_count = sum(tile is not None for tile in board.tiles.flat)
    return (
        f"Built-in Civ-like map: {tile_count} tiles, "
        f"{len(board.rivers)} river segments, "
        f"terrain={dict(terrain_counts)}, "
        f"resources={resource_count}, "
        f"starting_city={board.starting_city_center}"
    )
