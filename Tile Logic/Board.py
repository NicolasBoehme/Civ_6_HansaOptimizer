from typing import Tuple, Optional, List
import numpy as np
from Tile import Tile
from River import River


# Double-width neighbour offsets: (dcol, drow)
_NEIGHBOUR_OFFSETS: List[Tuple[int, int]] = [
    (2, 0), (-2, 0),
    (1, -1), (-1, -1),
    (1, 1), (-1, 1),
]


class Board:
    def __init__(self):
        self.tiles: np.ndarray = np.empty((0, 0), dtype=object)
        self.rivers: List[River] = []
        self._coord_index: dict = {}  # id(tile) -> (col, row)

    def setBoard(self, board: np.ndarray):
        self.tiles = board
        self._coord_index = {}
        rows, cols = board.shape
        for r in range(rows):
            for c in range(cols):
                t = board[r, c]
                if t is not None:
                    self._coord_index[id(t)] = (c, r)

    def setTile(self, tile: Tile, coordinates: Tuple[int, int]):
        col, row = coordinates
        self.tiles[row, col] = tile
        self._coord_index[id(tile)] = (col, row)

    def tile_coords(self, tile: Tile) -> Tuple[int, int]:
        return self._coord_index[id(tile)]

    def _in_bounds(self, col: int, row: int) -> bool:
        rows, cols = self.tiles.shape
        return 0 <= row < rows and 0 <= col < cols

    def getNeighbours(
        self, tile: Tile
    ) -> Tuple[Optional[Tile], Optional[Tile], Optional[Tile],
              Optional[Tile], Optional[Tile], Optional[Tile]]:
        col, row = self.tile_coords(tile)
        out = []
        for dc, dr in _NEIGHBOUR_OFFSETS:
            nc, nr = col + dc, row + dr
            if self._in_bounds(nc, nr):
                out.append(self.tiles[nr, nc])
            else:
                out.append(None)
        return tuple(out)  # type: ignore[return-value]

    def areNeighbours(self, tile1: Tile, tile2: Tile) -> bool:
        c1, r1 = self.tile_coords(tile1)
        c2, r2 = self.tile_coords(tile2)
        return (c2 - c1, r2 - r1) in _NEIGHBOUR_OFFSETS
