from typing import List, Optional

from .fallback import FallbackInfeasible, fallback_solve
from .fit import (
    CityPlacement,
    Placement,
    StartingCity,
    _fit_template_with_start,
    fit_best,
)
from .templates import DOUBLE_2, TRIANGLE_3, load_default_library


def _score_placement(board, sc, cities: List[CityPlacement]) -> int:
    from .score import score_total

    full = Placement(
        cities=tuple(cities),
        score=0,
        template_name=None,
        anchor=None,
        rotation=None,
        mirror=None,
        instance=None,
    )
    return score_total(board, full, starting_city=sc)


def _peel_template_then_fill(board, sc, n) -> Optional[Placement]:
    """When no exact-match composite fits, anchor a single template (with the
    starting city as host) and fill the remaining new-city slots via fallback.

    This keeps the AQ-anchored triangle / double cluster discipline intact for
    the bulk of the placement instead of degrading to fully greedy isolated
    cities when n+1 doesn't match a registered template count.
    """
    total = n + 1
    candidates = []
    if total >= 3:
        candidates.append((TRIANGLE_3, 3))
    if total >= 2:
        candidates.append((DOUBLE_2, 2))

    best: Optional[Placement] = None
    for template, template_cities in candidates:
        anchor = _fit_template_with_start(board, template, sc)
        if anchor is None:
            continue
        remaining = total - template_cities
        prefilled = list(anchor.cities)
        if remaining == 0:
            placement = anchor
        else:
            try:
                extended = fallback_solve(board, sc, remaining, prefilled=prefilled)
            except FallbackInfeasible:
                continue
            placement = Placement(
                cities=extended.cities,
                score=_score_placement(board, sc, list(extended.cities)),
                template_name=f"{template.name}+fallback",
                anchor=None,
                rotation=None,
                mirror=None,
                instance=None,
            )
        if best is None or placement.score > best.score:
            best = placement
    return best


def solve(board, starting_city, n, *, library=None, progress_callback=None) -> Placement:
    if n < 0:
        raise ValueError("n must be non-negative")

    sc = StartingCity.from_dict(starting_city, board)
    if n == 0:
        return Placement(
            cities=(),
            score=0,
            template_name=None,
            anchor=None,
            rotation=None,
            mirror=None,
            instance=None,
        )

    lib = library or load_default_library()
    if progress_callback is not None:
        progress_callback(0, 3, "fitting templates")

    placement: Optional[Placement] = fit_best(board, lib, sc, n)
    if progress_callback is not None:
        progress_callback(1, 3, "templates done")

    if placement is None:
        peeled = _peel_template_then_fill(board, sc, n)
        if progress_callback is not None:
            progress_callback(2, 3, "template+fallback")
        if peeled is not None:
            placement = peeled
        else:
            placement = fallback_solve(board, sc, n)
    else:
        if progress_callback is not None:
            progress_callback(2, 3, "template+fallback")

    if progress_callback is not None:
        progress_callback(3, 3, "done")
    return placement
