"""Data classes for the optimizer.

Coordinates are double-width (col, row) tuples throughout the public API.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .hex import Coord


# District kinds the optimizer reasons about.
H = "hansa"
CH = "commhub"
HB = "harbor"
AQ = "aqueduct"
OTHER = "other"


# Scoring modes.
HANSA_ONLY = "hansa_only"
COMBINATION = "combination"


@dataclass
class City:
    coords: Coord
    coastal_flag: bool
    aqueduct_candidates: List[Coord]
    hansa_candidates: List[Coord]
    commhub_candidates: List[Coord]
    harbor_candidates: List[Coord]
    high_synergy: bool = False
    is_existing: bool = False
    fixed_assignment: Optional["Assignment"] = None  # for the starting city


@dataclass
class Cluster:
    cities: List[City]


@dataclass
class Assignment:
    hansa: Optional[Coord] = None
    commhub: Optional[Coord] = None
    harbor: Optional[Coord] = None
    aqueduct: Optional[Coord] = None


@dataclass
class Score:
    production: int = 0
    gold: int = 0

    def weighted(self, w: float) -> float:
        return self.production + w * self.gold

    def __add__(self, other: "Score") -> "Score":
        return Score(self.production + other.production, self.gold + other.gold)


@dataclass
class CityResult:
    city: City
    assignment: Assignment
    score: Score


@dataclass
class Solution:
    cities: List[CityResult] = field(default_factory=list)
    score: Score = field(default_factory=Score)
    mode: str = HANSA_ONLY
    exchange_rate: float = 1.0

    def weighted_total(self) -> float:
        if self.mode == HANSA_ONLY:
            return float(self.score.production)
        return self.score.weighted(self.exchange_rate)


# Convenience type aliases used by the inner loops.
PlacementMap = Dict[Tuple[int, str], Coord]   # (city_idx, kind) -> coord
TileOwners = Dict[Coord, Tuple[int, str]]     # coord -> (city_idx, kind)
