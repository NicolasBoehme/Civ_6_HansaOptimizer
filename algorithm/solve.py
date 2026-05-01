from typing import Optional

from .fallback import fallback_solve
from .fit import Placement, StartingCity
from .group_search import fit_preferred_patterns


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

    del library
    if progress_callback is not None:
        progress_callback(0, 3, "fitting groups")

    placement: Optional[Placement] = fit_preferred_patterns(board, sc, n)
    if progress_callback is not None:
        progress_callback(1, 3, "groups done")

    if placement is None:
        if progress_callback is not None:
            progress_callback(2, 3, "fallback")
        placement = fallback_solve(board, sc, n)
    else:
        if progress_callback is not None:
            progress_callback(2, 3, "fallback")

    if progress_callback is not None:
        progress_callback(3, 3, "done")
    return placement
