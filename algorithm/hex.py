from typing import Iterable, List, Set, Tuple


Coord = Tuple[int, int]

NEIGHBOUR_OFFSETS: Tuple[Coord, ...] = (
    (2, 0),
    (1, -1),
    (-1, -1),
    (-2, 0),
    (-1, 1),
    (1, 1),
)


def add(a: Coord, b: Coord) -> Coord:
    return a[0] + b[0], a[1] + b[1]


def sub(a: Coord, b: Coord) -> Coord:
    return a[0] - b[0], a[1] - b[1]


def _to_cube(coord: Coord) -> Tuple[int, int, int]:
    col, row = coord
    x = (col - row) // 2
    z = row
    y = -x - z
    return x, y, z


def _from_cube(cube: Tuple[int, int, int]) -> Coord:
    x, _y, z = cube
    return 2 * x + z, z


def neighbours(c: Coord) -> List[Coord]:
    return [add(c, offset) for offset in NEIGHBOUR_OFFSETS]


def distance(a: Coord, b: Coord) -> int:
    ax, ay, az = _to_cube(a)
    bx, by, bz = _to_cube(b)
    return (abs(ax - bx) + abs(ay - by) + abs(az - bz)) // 2


def tiles_within_radius(center: Coord, r: int) -> Set[Coord]:
    out: Set[Coord] = set()
    parity = (center[0] + center[1]) % 2
    for col in range(center[0] - 2 * r, center[0] + 2 * r + 1):
        for row in range(center[1] - r, center[1] + r + 1):
            coord = (col, row)
            if (col + row) % 2 != parity:
                continue
            if distance(center, coord) <= r:
                out.add(coord)
    return out


def rotate_offset(offset: Coord, k: int) -> Coord:
    cube = _to_cube(offset)
    for _ in range(k % 6):
        x, y, z = cube
        cube = (-z, -x, -y)
    return _from_cube(cube)


def mirror_offset(offset: Coord) -> Coord:
    x, y, z = _to_cube(offset)
    return _from_cube((x, z, y))


def rotate_offsets(offsets: Iterable[Coord], k: int, mirror: bool = False) -> List[Coord]:
    rotated: List[Coord] = []
    for offset in offsets:
        current = mirror_offset(offset) if mirror else offset
        rotated.append(rotate_offset(current, k))
    return rotated
