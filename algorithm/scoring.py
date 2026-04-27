"""Benefit matrix, scoring primitives, and the influence field.

Scoring decomposes into:
- Hansa production:     +2 per adj CH/HB/Aq, +1 per adj other district / Hansa,
                        +2 per adj luxury|strategic, +1 per adj bonus.
- CommHub gold:         +2 per adj river-endpoint tile, +1 per adj district.
- Harbor gold:          +1 per adj district (base gold from tile data is omitted —
                        the brief says treat it as fixed per-tile, we keep it 0
                        until the map encodes it).

All cross-city adjacencies use the same matrix; ownership is irrelevant.
"""
from typing import Dict, Optional, Tuple

from .features import FeatureMap, TileFeatures
from .hex import Coord, neighbours
from .model import (AQ, CH, H, HB, OTHER, Assignment, City, PlacementMap,
                    Score, TileOwners)


# Hansa production gained per neighbour kind.
HANSA_GAIN = {
    H: 1,
    CH: 2,
    HB: 2,
    AQ: 2,
    OTHER: 1,
}

# Reciprocal contributions when a Hansa is adjacent.
CH_GAIN_FROM_HANSA = 1   # gold
HB_GAIN_FROM_HANSA = 1   # gold
# Aqueduct receives nothing.

# CH/HB cross-bonus.
CH_GAIN_FROM_HB = 1
HB_GAIN_FROM_CH = 1


def resource_bonus(feat: Optional[TileFeatures]) -> int:
    if feat is None or feat.resource_tier is None:
        return 0
    return 2 if feat.resource_tier in ("luxury", "strategic") else 1


def hansa_neighbour_kind(
    coord: Coord,
    feature_map: FeatureMap,
    owners: TileOwners,
) -> Optional[str]:
    """What kind of district sits at `coord` for Hansa-adjacency scoring?

    Returns one of H/CH/HB/AQ/OTHER, or None if no district.
    """
    owned = owners.get(coord)
    if owned is not None:
        return owned[1]
    feat = feature_map.get(coord)
    if feat is None or feat.existing_district_kind is None:
        return None
    return feat.existing_district_kind


def score_hansa_at(
    tile: Coord,
    feature_map: FeatureMap,
    owners: TileOwners,
) -> int:
    total = 0
    for n in neighbours(tile):
        kind = hansa_neighbour_kind(n, feature_map, owners)
        if kind is not None:
            total += HANSA_GAIN[kind]
        total += resource_bonus(feature_map.get(n))
    return total


def score_ch_at(
    tile: Coord,
    feature_map: FeatureMap,
    owners: TileOwners,
) -> int:
    """Gold from a CommHub at `tile`."""
    total = 0
    for n in neighbours(tile):
        feat = feature_map.get(n)
        if feat is not None and feat.is_river_endpoint:
            total += 2
        kind = hansa_neighbour_kind(n, feature_map, owners)
        if kind is not None:
            total += 1
    return total


def score_hb_at(
    tile: Coord,
    feature_map: FeatureMap,
    owners: TileOwners,
) -> int:
    """Gold from a Harbor at `tile` (base trade gold is map-fixed; not modeled)."""
    total = 0
    for n in neighbours(tile):
        kind = hansa_neighbour_kind(n, feature_map, owners)
        if kind is not None:
            total += 1
    return total


def score_assignment(
    cities: list, assignments: Dict[int, Assignment], feature_map: FeatureMap
) -> Score:
    owners: TileOwners = {}
    for ci, a in assignments.items():
        if a.hansa is not None:
            owners[a.hansa] = (ci, H)
        if a.commhub is not None:
            owners[a.commhub] = (ci, CH)
        if a.harbor is not None:
            owners[a.harbor] = (ci, HB)
        if a.aqueduct is not None:
            owners[a.aqueduct] = (ci, AQ)

    production = 0
    gold = 0
    for ci, a in assignments.items():
        if a.hansa is not None:
            production += score_hansa_at(a.hansa, feature_map, owners)
        if a.commhub is not None:
            gold += score_ch_at(a.commhub, feature_map, owners)
        if a.harbor is not None:
            gold += score_hb_at(a.harbor, feature_map, owners)
    return Score(production=production, gold=gold)


def compute_influence_field(feature_map: FeatureMap) -> Dict[Coord, int]:
    """IF(t) = what a Hansa placed at t gains from already-fixed elements:
    starting-city districts and resources on neighbouring tiles.
    """
    out: Dict[Coord, int] = {}
    for coord, feat in feature_map.items():
        total = 0
        for n in neighbours(coord):
            nf = feature_map.get(n)
            if nf is None:
                continue
            if nf.existing_district_kind is not None:
                total += HANSA_GAIN[nf.existing_district_kind]
            total += resource_bonus(nf)
        out[coord] = total
    return out
