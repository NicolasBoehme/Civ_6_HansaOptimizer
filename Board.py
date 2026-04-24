from Tile import Tile
from River import River
import numpy as np
class Board:
    rivers = list[River]
    tiles = np.array([],dtype=Tile)

    def tile_coords(tile:Tile) -> tuple[int,int]:
        pass