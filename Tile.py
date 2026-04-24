class Tile:
    terrain = "None"
    """
    plains, hills, mountains, coast, ocean, reef, wonder
    """
    def __init__(self, terrain):
        self.terrain = terrain