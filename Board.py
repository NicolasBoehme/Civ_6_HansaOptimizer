from typing import Tuple, Optional
from Tile import Tile
from River import River
import numpy as np
class Board:
    rivers = list[River]
    tiles = np.array([],dtype=Tile)

    def tile_coords(self,tile:Tile) -> Tuple[int,int]:
        pass

    def getNeighbours(self, tile:Tile) -> Tuple[Optional[Tile], Optional[Tile], Optional[Tile], Optional[Tile], Optional[Tile], Optional[Tile]]:
        pass

    def areNeighbours(self, tile1:Tile,tile2:Tile) -> bool:
        pass

    def addTile(self, tile:Tile, coordinates:Tuple[int,int]):
        self.tiles[coordinates[0],coordinates[1]] = tile