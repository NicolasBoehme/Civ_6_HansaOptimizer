from typing import Tuple, Optional
from Tile import Tile
from River import River
import numpy as np
class Board:
    rivers = list[River]
    tiles = np.array([],dtype=Tile)

    def tile_coords(tile:Tile) -> Tuple[int,int]:
        pass

    def getNeighbours(tile:Tile) -> Tuple[Optional[Tile], Optional[Tile], Optional[Tile], Optional[Tile], Optional[Tile], Optional[Tile]]:
        pass

    def isNeighbour(tile:Tile) -> bool:
        pass