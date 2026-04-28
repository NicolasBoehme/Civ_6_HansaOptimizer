"""Candidate generation: city-center filtering and per-city candidate sets."""
from typing import List

from .features import FeatureMap
from .hex import Coord, distance, disk, neighbours
from .model import AQ, CH, H, HB, City


def _aqueduct_candidates_for(center: Coord,
                             feature_map: FeatureMap) -> List[Coord]:
    """Tiles within distance 1 of `center` that are placeable AND adjacent to
    river / lake / mountain.
    """
    out: List[Coord] = []
    for n in neighbours(center):
        feat = feature_map.get(n)
        if feat is None or not feat.placeable:
            continue
        if feat.aqueduct_feature:
            out.append(n)
    return out


def _placeable_in_radius(center: Coord, r: int,
                         feature_map: FeatureMap) -> List[Coord]:
    out: List[Coord] = []
    for c in disk(center, r):
        if c == center:
            continue
        feat = feature_map.get(c)
        if feat is None or not feat.placeable:
            continue
        out.append(c)
    return out


def build_city(coords: Coord, feature_map: FeatureMap,
               is_existing: bool = False) -> City:
    placeable = _placeable_in_radius(coords, 3, feature_map)
    coastal = [c for c in placeable if feature_map[c].is_coastal]
    aq = _aqueduct_candidates_for(coords, feature_map)
    return City(
        coords=coords,
        coastal_flag=any(feature_map[c].is_coastal for c in placeable),
        aqueduct_candidates=aq,
        hansa_candidates=list(placeable),
        commhub_candidates=list(placeable),
        harbor_candidates=coastal,
        is_existing=is_existing,
    )


def enumerate_city_centers(
    feature_map: FeatureMap,
    existing_centers: List[Coord],
    min_spacing: int = 4,
) -> List[City]:
    """Tiles eligible to host a NEW city center.

    Excludes water / mountain / wonder, tiles already holding any optimised
    district, and tiles within `min_spacing` of any existing center.
    """
    candidates: List[City] = []
    for coords, feat in feature_map.items():
        if feat.is_water or feat.is_mountain or feat.is_wonder:
            continue
        if feat.existing_district_kind is not None:
            continue
        if any(distance(coords, ec) < min_spacing for ec in existing_centers):
            continue
        candidates.append(build_city(coords, feature_map, is_existing=False))
    return candidates
