from typing import Optional


class Resource:
    BONUS = "bonus"
    LUXURY = "luxury"
    STRATEGIC = "strategic"

    def __init__(self, name: str, tier: str):
        if tier not in (Resource.BONUS, Resource.LUXURY, Resource.STRATEGIC):
            raise ValueError(f"unknown resource tier: {tier}")
        self.name = name
        self.tier = tier


class District:
    HANSA = "hansa"
    COMMHUB = "commhub"
    HARBOR = "harbor"
    AQUEDUCT = "aqueduct"
    OTHER = "other"

    def __init__(self, kind: str, city_id: Optional[int] = None):
        self.kind = kind
        self.city_id = city_id


class Tile:
    """
    terrain: plains, hills, mountains, coast, ocean, reef, wonder, lake
    contains: optional contents layer — Resource, District, or anything
              else the map wants to attach to this tile (mine, etc.).
    """

    def __init__(self, terrain: str, contains: Optional[object] = None):
        self.terrain = terrain
        self.contains = contains
