"""Per-tile feature extraction.

Reads the Board / Tile / River objects (duck-typed) and produces a
TileFeatures dict keyed by double-width (col, row).
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

from .hex import Coord, neighbours

WATER_TERRAINS = {"coast", "ocean", "reef", "lake"}
MOUNTAIN_TERRAINS = {"mountains"}
WONDER_TERRAINS = {"wonder"}
LAKE_TERRAINS = {"lake"}


@dataclass
class TileFeatures:
    coords: Coord
    terrain: str
    is_water: bool
    is_mountain: bool
    is_wonder: bool
    is_lake: bool
    is_river_endpoint: bool          # tile is endpoint of any River edge
    is_coastal: bool                 # adjacent to water
    aqueduct_feature: bool           # river / lake / mountain — feeds aqueduct
    resource_tier: Optional[str]     # 'bonus' | 'luxury' | 'strategic'
    existing_district_kind: Optional[str]
    placeable: bool                  # can host a new district


FeatureMap = Dict[Coord, TileFeatures]


def _resource_tier(contains: Any) -> Optional[str]:
    tier = getattr(contains, "tier", None)
    if tier in ("bonus", "luxury", "strategic"):
        return tier
    return None


def _district_kind(contains: Any) -> Optional[str]:
    kind = getattr(contains, "kind", None)
    if kind in ("hansa", "commhub", "harbor", "aqueduct", "other"):
        return kind
    return None


def extract_features(board: Any) -> FeatureMap:
    tiles = board.tiles
    rows, cols = tiles.shape

    # Collect river-endpoint tiles by identity.
    river_endpoints: Set[int] = set()
    for r in getattr(board, "rivers", []) or []:
        t1, t2 = r.getTiles()
        river_endpoints.add(id(t1))
        river_endpoints.add(id(t2))

    out: FeatureMap = {}
    for row in range(rows):
        for col in range(cols):
            tile = tiles[row, col]
            if tile is None:
                continue
            coords: Coord = (col, row)
            terrain = getattr(tile, "terrain", "None")
            contains = getattr(tile, "contains", None)

            is_water = terrain in WATER_TERRAINS
            is_mountain = terrain in MOUNTAIN_TERRAINS
            is_wonder = terrain in WONDER_TERRAINS
            is_lake = terrain in LAKE_TERRAINS
            is_river_endpoint = id(tile) in river_endpoints

            res_tier = _resource_tier(contains)
            dist_kind = _district_kind(contains)

            placeable = not (is_water or is_mountain or is_wonder) and dist_kind is None

            out[coords] = TileFeatures(
                coords=coords,
                terrain=terrain,
                is_water=is_water,
                is_mountain=is_mountain,
                is_wonder=is_wonder,
                is_lake=is_lake,
                is_river_endpoint=is_river_endpoint,
                is_coastal=False,         # filled below
                aqueduct_feature=False,   # filled below
                resource_tier=res_tier,
                existing_district_kind=dist_kind,
                placeable=placeable,
            )

    # Second pass: coastal + aqueduct-feature (depend on neighbours).
    for coords, feat in out.items():
        for n in neighbours(coords):
            nf = out.get(n)
            if nf is None:
                continue
            if nf.is_water:
                feat.is_coastal = True
            # Aqueduct needs a neighbour that is river / lake / mountain.
            if nf.is_river_endpoint or nf.is_lake or nf.is_mountain:
                feat.aqueduct_feature = True

    # Aqueduct candidate tile itself just needs the *feature* of having any
    # such neighbour — we keep aqueduct_feature semantically as "this tile is
    # adjacent to a river/lake/mountain".
    return out
