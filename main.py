"""Civ 6 Hansa Optimizer — entry point."""
import sys
import time
from typing import Any, Optional, Tuple

from algorithm import HANSA_ONLY, COMBINATION, solve
from test_board import board_summary, build_three_river_plains_board
from visualizer import show_solution


class TerminalProgressBar:
    def __init__(self, width: int = 30):
        self.width = width
        self._last_line_len = 0
        self._last_draw = 0.0
        self._last_percent = -1
        self._interactive = sys.stdout.isatty()

    def update(self, completed: int, total: int, message: str) -> None:
        total = max(total, 1)
        ratio = min(max(completed / total, 0.0), 1.0)
        percent = int(ratio * 100)
        now = time.time()

        should_draw = (
            completed == 0
            or completed >= total
            or percent != self._last_percent
            or (self._interactive and (now - self._last_draw) >= 0.1)
        )
        if not should_draw:
            return

        self._last_draw = now
        self._last_percent = percent
        filled = int(self.width * ratio)
        bar = "#" * filled + "-" * (self.width - filled)
        line = f"Solving [{bar}] {percent:3d}% ({completed}/{total}) {message}"

        if self._interactive:
            padding = max(0, self._last_line_len - len(line))
            print("\r" + line + (" " * padding), end="", flush=True)
            if completed >= total:
                print()
        else:
            print(line, flush=True)
        self._last_line_len = len(line)


def load_board() -> Tuple[Optional[Any], Optional[dict]]:
    """Return the built-in hypothetical test board."""
    return build_three_river_plains_board()


def main() -> int:
    raw = input("Number of new cities to place (N): ").strip()
    try:
        n = int(raw)
    except ValueError:
        print(f"Invalid N: {raw!r}")
        return 1
    if n < 0:
        print("N must be non-negative.")
        return 1

    mode = input("Mode [hansa_only / combination] (default hansa_only): ").strip() \
        or HANSA_ONLY
    if mode not in (HANSA_ONLY, COMBINATION):
        print(f"Unknown mode: {mode!r}")
        return 1

    exchange_rate = 1.0
    if mode == COMBINATION:
        rate_raw = input("Exchange rate W (1 prod = W gold, default 1.0): ").strip()
        if rate_raw:
            try:
                exchange_rate = float(rate_raw)
            except ValueError:
                print(f"Invalid exchange rate: {rate_raw!r}")
                return 1

    board, starting_city = load_board()
    if board is None:
        print("Map input not available.")
        print(f"Configured: N={n}, mode={mode}, exchange_rate={exchange_rate}")
        return 0
    print(board_summary(board))
    progress = TerminalProgressBar()

    solution = solve(
        board=board,
        starting_city=starting_city,
        n=n,
        mode=mode,
        exchange_rate=exchange_rate,
        progress_callback=progress.update,
    )

    print(f"Total: production={solution.score.production}, "
          f"gold={solution.score.gold}, "
          f"weighted={solution.weighted_total():.2f}")
    for cr in solution.cities:
        a = cr.assignment
        print(f"  City @ {cr.city.coords}: "
              f"H={a.hansa} CH={a.commhub} HB={a.harbor} AQ={a.aqueduct} "
              f"score(prod={cr.score.production}, gold={cr.score.gold})")
    print("Solve complete. Opening viewer; close the window to end the run.")
    show_solution(board, solution, focus_radius=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
