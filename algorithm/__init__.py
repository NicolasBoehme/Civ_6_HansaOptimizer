"""Civ 6 Hansa placement optimiser — Solution A.

Public entry point: `solve(board, starting_city, n, mode, exchange_rate)`.
"""
from .model import (Assignment, City, CityResult, Cluster, Score, Solution,
                    HANSA_ONLY, COMBINATION, H, CH, HB, AQ, OTHER)
from .solve import solve

__all__ = [
    "solve",
    "Solution",
    "Score",
    "Assignment",
    "City",
    "CityResult",
    "Cluster",
    "HANSA_ONLY",
    "COMBINATION",
    "H",
    "CH",
    "HB",
    "AQ",
    "OTHER",
]
