"""Hex geometry: double-width grid + cube conversion.

The map is stored in double-width coords (col, row); the math spec works in
cube coords. We convert at the boundary and use cube for distance.
"""
from typing import Iterator, List, Tuple

Coord = Tuple[int, int]            # (col, row), double-width
Cube = Tuple[int, int, int]        # (x, y, z), x+y+z = 0

# Double-width neighbour offsets (matches Tile Logic/Board.py).
NEIGHBOUR_OFFSETS: List[Coord] = [
    (2, 0), (-2, 0),
    (1, -1), (-1, -1),
    (1, 1), (-1, 1),
]


def to_cube(c: Coord) -> Cube:
    col, row = c
    x = (col - row) // 2
    z = row
    y = -x - z
    return (x, y, z)


def cube_distance(a: Cube, b: Cube) -> int:
    return (abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])) // 2


def distance(a: Coord, b: Coord) -> int:
    return cube_distance(to_cube(a), to_cube(b))


def neighbours(c: Coord) -> List[Coord]:
    col, row = c
    return [(col + dc, row + dr) for dc, dr in NEIGHBOUR_OFFSETS]


def are_adjacent(a: Coord, b: Coord) -> bool:
    return (b[0] - a[0], b[1] - a[1]) in NEIGHBOUR_OFFSETS


def disk(center: Coord, r: int) -> Iterator[Coord]:
    """All double-width coords within hex distance r (inclusive)."""
    if r < 0:
        return
    parity = (center[0] + center[1]) & 1
    for dr in range(-r, r + 1):
        for dc in range(-2 * r, 2 * r + 1):
            col, row = center[0] + dc, center[1] + dr
            if ((col + row) & 1) != parity:
                continue  # invalid double-width parity
            if distance(center, (col, row)) <= r:
                yield (col, row)


def ring(center: Coord, r: int) -> Iterator[Coord]:
    """All double-width coords at exactly hex distance r."""
    if r == 0:
        yield center
        return
    for c in disk(center, r):
        if distance(center, c) == r:
            yield c
