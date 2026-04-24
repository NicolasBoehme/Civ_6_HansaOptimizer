from Tile import Tile
from Board import Board
from typing import Tuple
class River:
    tile1: Tile
    tile2: Tile
    def __init__(self, board:Board, tile1:Tile, tile2:Tile):
        if(tile1 is tile2):
            raise ValueError("River got the same Tile twice")
        if(not board.isNeighbour(tile1, tile2)):
            raise ValueError("River got 2 tiles, but they were not adjacent")
        self.tile1 = tile1
        self.tile2 = tile2
    
    def getTiles(self) -> Tuple[Tile, Tile]:
        return (self.tile1, self.tile2)