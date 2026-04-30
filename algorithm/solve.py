from typing import Optional

from .fallback import fallback_solve
from .fit import Placement, StartingCity, fit_best
from .templates import load_default_library


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
        progress_callback(0, 2, "fitting templates")

    placement: Optional[Placement] = fit_best(board, lib, sc, n)
    if progress_callback is not None:
        progress_callback(1, 2, "templates done")

    if placement is None:
        placement = fallback_solve(board, sc, n)

    if progress_callback is not None:
        progress_callback(2, 2, "done")
    return placement
