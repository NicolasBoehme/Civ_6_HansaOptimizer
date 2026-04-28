"""Desktop visualization for solved Civ 6 Hansa boards.

Uses tkinter so the project does not depend on third-party GUI packages.
The default view is cropped to tiles within 2 hexes of any solved city or
district tile so the window stays compact.
"""
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - platform packaging issue
    tk = None

from algorithm import AQ, CH, H, HB, Solution
from algorithm.hex import Coord, distance


HEX_SIZE = 28
PADDING = 36
SIDEBAR_WIDTH = 290
HEADER_HEIGHT = 72

TERRAIN_FILL = {
    "plains": "#d5c391",
    "hills": "#b79263",
    "mountains": "#8d8f92",
    "coast": "#80b8d8",
    "ocean": "#5d92c0",
    "reef": "#6ec4bf",
    "wonder": "#d48d4f",
    "lake": "#7cb4dd",
}

# Tint applied to plains/hills tiles that touch a river edge so the corridor
# reads at a glance even before the edge lines are drawn.
RIVER_TILE_TINT = {
    "plains": "#cdc096",
    "hills": "#b09668",
}

RIVER_EDGE_COLOR = "#1c6dc8"
RIVER_EDGE_HIGHLIGHT = "#7fb6e8"
RIVER_EDGE_WIDTH = 9
RIVER_EDGE_HIGHLIGHT_WIDTH = 3

DISTRICT_STYLE = {
    H: {"fill": "#cb7a52", "label": "H"},
    CH: {"fill": "#f2d16b", "label": "CH"},
    HB: {"fill": "#5ea4c6", "label": "HB"},
    AQ: {"fill": "#80ba72", "label": "AQ"},
}


@dataclass
class RenderCity:
    label: str
    center: Coord
    hansa: Optional[Coord]
    commhub: Optional[Coord]
    harbor: Optional[Coord]
    aqueduct: Optional[Coord]
    production: int
    gold: int


def _board_coords(board) -> List[Coord]:
    rows, cols = board.tiles.shape
    coords: List[Coord] = []
    for row in range(rows):
        for col in range(cols):
            if board.tiles[row, col] is not None:
                coords.append((col, row))
    return coords


def _city_label(coord: Coord, board, next_city_index: int) -> str:
    if coord == getattr(board, "starting_city_center", None):
        return "S"
    return f"C{next_city_index}"


def _render_cities(board, solution: Solution) -> List[RenderCity]:
    cities: List[RenderCity] = []
    next_city_index = 1
    for result in solution.cities:
        label = _city_label(result.city.coords, board, next_city_index)
        if label.startswith("C"):
            next_city_index += 1
        cities.append(RenderCity(
            label=label,
            center=result.city.coords,
            hansa=result.assignment.hansa,
            commhub=result.assignment.commhub,
            harbor=result.assignment.harbor,
            aqueduct=result.assignment.aqueduct,
            production=result.score.production,
            gold=result.score.gold,
        ))
    return cities


def _focus_coords(render_cities: Sequence[RenderCity]) -> Set[Coord]:
    focus: Set[Coord] = set()
    for city in render_cities:
        focus.add(city.center)
        for coord in (city.hansa, city.commhub, city.harbor, city.aqueduct):
            if coord is not None:
                focus.add(coord)
    return focus


def _visible_coords(board, render_cities: Sequence[RenderCity], focus_radius: int) -> List[Coord]:
    coords = _board_coords(board)
    focus = _focus_coords(render_cities)
    if not focus:
        start = getattr(board, "starting_city_center", None)
        if start is not None:
            focus = {start}
    if not focus:
        return coords
    return [
        coord for coord in coords
        if any(distance(coord, f) <= focus_radius for f in focus)
    ]


def _coord_to_pixel(coord: Coord) -> Tuple[float, float]:
    col, row = coord
    q = (col - row) // 2
    r = row
    x = HEX_SIZE * math.sqrt(3) * (q + r / 2)
    y = HEX_SIZE * 1.5 * r
    return x, y


def _hex_points(cx: float, cy: float) -> List[float]:
    points: List[float] = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        points.extend((
            cx + HEX_SIZE * math.cos(angle),
            cy + HEX_SIZE * math.sin(angle),
        ))
    return points


def _district_at(coord: Coord, render_cities: Sequence[RenderCity]) -> Optional[Tuple[str, str]]:
    for city in render_cities:
        for kind, tile in (
            (H, city.hansa),
            (CH, city.commhub),
            (HB, city.harbor),
            (AQ, city.aqueduct),
        ):
            if tile == coord:
                style = DISTRICT_STYLE[kind]
                return style["label"], style["fill"]
    return None


def _city_at(coord: Coord, render_cities: Sequence[RenderCity]) -> Optional[RenderCity]:
    for city in render_cities:
        if city.center == coord:
            return city
    return None


def _tile_lookup(board) -> Dict[int, Coord]:
    lookup: Dict[int, Coord] = {}
    rows, cols = board.tiles.shape
    for row in range(rows):
        for col in range(cols):
            tile = board.tiles[row, col]
            if tile is not None:
                lookup[id(tile)] = (col, row)
    return lookup


def _river_segments(board, visible: Set[Coord]) -> List[Tuple[Coord, Coord]]:
    segments: List[Tuple[Coord, Coord]] = []
    tile_lookup = _tile_lookup(board)
    for river in getattr(board, "rivers", []) or []:
        t1, t2 = river.getTiles()
        c1 = tile_lookup.get(id(t1))
        c2 = tile_lookup.get(id(t2))
        if c1 is not None and c2 is not None and c1 in visible and c2 in visible:
            segments.append((c1, c2))
    return segments


def _river_tile_set(board) -> Set[Coord]:
    """All tile coords that sit on at least one river edge (i.e. river-endpoint
    tiles). The visualiser uses this to tint the tile background and outline
    river-touching hexes so the corridor reads even when several edges overlap.
    """
    tiles: Set[Coord] = set()
    tile_lookup = _tile_lookup(board)
    for river in getattr(board, "rivers", []) or []:
        t1, t2 = river.getTiles()
        for tile in (t1, t2):
            coord = tile_lookup.get(id(tile))
            if coord is not None:
                tiles.add(coord)
    return tiles


def _river_edge_pixels(left: Coord, right: Coord) -> Tuple[float, float, float, float]:
    x1, y1 = _coord_to_pixel(left)
    x2, y2 = _coord_to_pixel(right)
    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2

    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return mid_x, mid_y, mid_x, mid_y

    # Shared hex edge is perpendicular to the line between the two centers,
    # scaled to the actual edge length (HEX_SIZE / sqrt(3)) so the river line
    # neatly tracks the hex border without bleeding into adjacent tiles.
    perp_x = -dy / length
    perp_y = dx / length
    half_edge = (HEX_SIZE / math.sqrt(3))
    return (
        mid_x - perp_x * half_edge,
        mid_y - perp_y * half_edge,
        mid_x + perp_x * half_edge,
        mid_y + perp_y * half_edge,
    )


def _terrain_fill(board, coord: Coord, river_tiles: Set[Coord]) -> str:
    tile = board.tiles[coord[1], coord[0]]
    terrain = getattr(tile, "terrain", "plains")
    if coord in river_tiles and terrain in RIVER_TILE_TINT:
        return RIVER_TILE_TINT[terrain]
    return TERRAIN_FILL.get(terrain, "#d9d0b6")


def _summary_lines(board, solution: Solution, render_cities: Sequence[RenderCity], focus_radius: int) -> List[str]:
    lines = [
        f"Mode: {solution.mode}",
        f"Total prod: {solution.score.production}",
        f"Total gold: {solution.score.gold}",
        f"Weighted: {solution.weighted_total():.2f}",
        f"Focus crop: {focus_radius} hexes",
        "",
    ]
    for city in render_cities:
        lines.append(
            f"{city.label} @ {city.center}  prod={city.production} gold={city.gold}"
        )
        lines.append(
            f"  H={city.hansa} CH={city.commhub} HB={city.harbor} AQ={city.aqueduct}"
        )
    if not render_cities and getattr(board, "starting_city_center", None) is not None:
        lines.append(f"S @ {board.starting_city_center}")
    return lines


def show_solution(board, solution: Solution, focus_radius: int = 2) -> bool:
    """Open a compact Swing-style desktop view of the solved board."""
    if os.environ.get("HANSA_NO_GUI") == "1":
        return False
    if tk is None:
        print("Visualization skipped: tkinter is not available on this Python install.")
        return False

    try:
        root = tk.Tk()
    except Exception as exc:  # pragma: no cover - depends on local display
        print(f"Visualization skipped: could not open a window ({exc}).")
        return False

    render_cities = _render_cities(board, solution)
    visible_coords = _visible_coords(board, render_cities, focus_radius)
    if not visible_coords:
        visible_coords = _board_coords(board)
    visible = set(visible_coords)

    projected = [_coord_to_pixel(coord) for coord in visible_coords]
    min_x = min(x for x, _ in projected)
    max_x = max(x for x, _ in projected)
    min_y = min(y for _, y in projected)
    max_y = max(y for _, y in projected)

    width = int((max_x - min_x) + 2 * PADDING + 2 * HEX_SIZE + SIDEBAR_WIDTH)
    height = int((max_y - min_y) + 2 * PADDING + 2 * HEX_SIZE + HEADER_HEIGHT)
    x_offset = PADDING - min_x + HEX_SIZE
    y_offset = HEADER_HEIGHT - min_y + HEX_SIZE / 2

    root.title("Civ 6 Hansa Optimizer Viewer")
    root.geometry(f"{width}x{height}")

    canvas = tk.Canvas(root, width=width, height=height, bg="#f4efe5", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    canvas.create_text(
        PADDING,
        26,
        anchor="w",
        text="Civ 6 Hansa Optimizer",
        fill="#2d2a26",
        font=("Helvetica", 20, "bold"),
    )
    canvas.create_text(
        PADDING,
        52,
        anchor="w",
        text=f"Compact view: tiles within {focus_radius} hexes of each solved city or district.",
        fill="#655e53",
        font=("Helvetica", 10),
    )

    river_tiles = _river_tile_set(board)
    river_segments = _river_segments(board, visible)

    # Pass 1: tile polygons (with river-tinted fill / blue outline for river tiles).
    for coord in visible_coords:
        cx, cy = _coord_to_pixel(coord)
        cx += x_offset
        cy += y_offset
        city = _city_at(coord, render_cities)
        fill = _terrain_fill(board, coord, river_tiles)
        outline = "#7b6c57"
        width_px = 1
        if coord in river_tiles:
            outline = "#3a6a9c"
            width_px = 2
        if city is not None:
            outline = "#2e2d2d"
            width_px = 3
        canvas.create_polygon(
            _hex_points(cx, cy),
            fill=fill,
            outline=outline,
            width=width_px,
        )

    # Pass 2: rivers — drawn after polygons so the heavy blue line sits on top
    # of the tile borders. Each segment is a darker base line with a brighter
    # highlight stripe on top — readable even where several segments share a
    # junction tile.
    for left, right in river_segments:
        x1, y1, x2, y2 = _river_edge_pixels(left, right)
        canvas.create_line(
            x1 + x_offset, y1 + y_offset,
            x2 + x_offset, y2 + y_offset,
            fill=RIVER_EDGE_COLOR,
            width=RIVER_EDGE_WIDTH,
            capstyle=tk.ROUND,
        )
        canvas.create_line(
            x1 + x_offset, y1 + y_offset,
            x2 + x_offset, y2 + y_offset,
            fill=RIVER_EDGE_HIGHLIGHT,
            width=RIVER_EDGE_HIGHLIGHT_WIDTH,
            capstyle=tk.ROUND,
        )

    # Pass 3: per-tile overlays — district markers, city labels, coords.
    for coord in visible_coords:
        cx, cy = _coord_to_pixel(coord)
        cx += x_offset
        cy += y_offset
        city = _city_at(coord, render_cities)
        district = _district_at(coord, render_cities)

        if district is not None:
            label, color = district
            canvas.create_oval(
                cx - 14, cy - 14, cx + 14, cy + 14,
                fill=color, outline="#2d2a26", width=2,
            )
            canvas.create_text(
                cx, cy,
                text=label,
                fill="#1f1d1a",
                font=("Helvetica", 10, "bold"),
            )

        if city is not None:
            canvas.create_rectangle(
                cx - 18, cy + 10, cx + 18, cy + 28,
                fill="#2d2a26", outline="",
            )
            canvas.create_text(
                cx, cy + 19,
                text=city.label,
                fill="#f6f2e9",
                font=("Helvetica", 9, "bold"),
            )

        canvas.create_text(
            cx,
            cy - HEX_SIZE - 7,
            text=f"{coord[0]},{coord[1]}",
            fill="#6b6358",
            font=("Helvetica", 7),
        )

    sidebar_x = width - SIDEBAR_WIDTH + 18
    canvas.create_rectangle(
        width - SIDEBAR_WIDTH,
        0,
        width,
        height,
        fill="#ece3d4",
        outline="",
    )
    canvas.create_text(
        sidebar_x,
        24,
        anchor="nw",
        text="Summary",
        fill="#2d2a26",
        font=("Helvetica", 16, "bold"),
    )
    canvas.create_text(
        sidebar_x,
        56,
        anchor="nw",
        text="\n".join(_summary_lines(board, solution, render_cities, focus_radius)),
        fill="#37332d",
        font=("Courier", 10),
    )

    legend_y = height - 170
    canvas.create_text(
        sidebar_x,
        legend_y,
        anchor="nw",
        text="Legend",
        fill="#2d2a26",
        font=("Helvetica", 14, "bold"),
    )
    legend_items = [
        ("S / C#", "#2d2a26"),
        ("H", DISTRICT_STYLE[H]["fill"]),
        ("CH", DISTRICT_STYLE[CH]["fill"]),
        ("AQ", DISTRICT_STYLE[AQ]["fill"]),
        ("HB", DISTRICT_STYLE[HB]["fill"]),
        ("River edge", RIVER_EDGE_COLOR),
    ]
    for idx, (label, color) in enumerate(legend_items):
        y = legend_y + 28 + idx * 24
        canvas.create_rectangle(sidebar_x, y, sidebar_x + 18, y + 18, fill=color, outline="")
        canvas.create_text(
            sidebar_x + 28,
            y + 9,
            anchor="w",
            text=label,
            fill="#37332d",
            font=("Helvetica", 10, "bold"),
        )

    root.mainloop()
    return True
