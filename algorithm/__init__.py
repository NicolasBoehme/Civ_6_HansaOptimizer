from dataclasses import dataclass
from typing import Optional

from . import hex
from .fit import CityPlacement, Placement, StartingCity
from .hex import Coord
from .score import AQ, CH, H, HB, OTHER, build_district_index, build_resource_index, score_hansa
from .solve import solve


HANSA_ONLY = "hansa_only"
COMBINATION = "combination"


@dataclass(frozen=True)
class _ScorePair:
    production: int
    gold: int = 0


@dataclass(frozen=True)
class _CityView:
    coords: Coord


@dataclass(frozen=True)
class _AssignmentView:
    hansa: Coord
    commhub: Coord
    harbor: Optional[Coord]
    aqueduct: Coord


@dataclass(frozen=True)
class _CityResult:
    city: _CityView
    assignment: _AssignmentView
    score: _ScorePair


class Solution:
    def __init__(self, placement: Placement, per_city_scores, mode: str = HANSA_ONLY):
        self._placement = placement
        self.mode = HANSA_ONLY if mode == COMBINATION else mode
        self.score = _ScorePair(production=placement.score, gold=0)
        self.cities = [self._adapt(city, per_city_scores[index]) for index, city in enumerate(placement.cities)]

    def weighted_total(self) -> float:
        return float(self.score.production)

    def _adapt(self, city: CityPlacement, production: int) -> _CityResult:
        return _CityResult(
            city=_CityView(coords=city.center),
            assignment=_AssignmentView(
                hansa=city.hansa,
                commhub=city.commhub,
                harbor=city.harbor,
                aqueduct=city.aqueduct,
            ),
            score=_ScorePair(production=production, gold=0),
        )


def solve_compat(
    board,
    starting_city,
    n,
    mode: str = HANSA_ONLY,
    exchange_rate: float = 1.0,
    progress_callback=None,
    library=None,
):
    del exchange_rate
    placement = solve(
        board,
        starting_city,
        n,
        library=library,
        progress_callback=progress_callback,
    )
    sc = StartingCity.from_dict(starting_city, board)
    resource_index = build_resource_index(board)
    district_index = build_district_index(placement, sc, board)
    per_city_scores = [
        score_hansa(board, city.hansa, district_index, resource_index).total
        for city in placement.cities
    ]
    return Solution(placement, per_city_scores=per_city_scores, mode=mode)


__all__ = [
    "solve",
    "solve_compat",
    "Solution",
    "Placement",
    "CityPlacement",
    "StartingCity",
    "Coord",
    "HANSA_ONLY",
    "COMBINATION",
    "H",
    "CH",
    "HB",
    "AQ",
    "OTHER",
    "hex",
]
