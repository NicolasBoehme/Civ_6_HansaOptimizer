from dataclasses import dataclass
from typing import Callable, Iterable, List, Literal, Optional, Protocol, Tuple

from .hex import Coord, neighbours


TRIANGLE_3_TARGET = 33
DOUBLE_2_TARGET = 15
COMPOSITE_5_TARGET = 48
PER_HANSA_MAX_TRIANGLE_3 = 11
MIN_CITY_SPACING = 4
WORKING_RADIUS = 3
CLUSTER_RADIUS = 6
ORIENTATIONS = 12

SlotRole = Literal["city_center", "hansa", "commhub", "harbor", "aqueduct"]


class TilePredicate(Protocol):
    name: str

    def __call__(self, board, coord: Coord) -> bool:
        ...


@dataclass(frozen=True)
class TemplateSlot:
    offset: Coord
    role: SlotRole
    city_index: int
    predicates: Tuple[TilePredicate, ...]
    optional: bool = False


@dataclass(frozen=True)
class Template:
    name: str
    n_cities: int
    slots: Tuple[TemplateSlot, ...]
    expected_score: int
    notes: str = ""


@dataclass(frozen=True)
class CompositeTemplate(Template):
    parts: Tuple[Template, ...] = ()


class TemplateLibrary:
    def __init__(self, templates: Iterable[Template]):
        self._templates = tuple(templates)

    def for_n(self, n: int) -> List[Template]:
        return [template for template in self._templates if template.n_cities == n]


@dataclass(frozen=True)
class _Predicate:
    name: str
    func: Callable[[object, Coord], bool]

    def __call__(self, board, coord: Coord) -> bool:
        return self.func(board, coord)


def _in_bounds(board, coord: Coord) -> bool:
    col, row = coord
    rows, cols = board.tiles.shape
    return 0 <= row < rows and 0 <= col < cols


def _get_tile(board, coord: Coord):
    if not _in_bounds(board, coord):
        return None
    return board.tiles[coord[1], coord[0]]


def _river_endpoint_coords(board) -> set[Coord]:
    tile_lookup = {}
    rows, cols = board.tiles.shape
    for row in range(rows):
        for col in range(cols):
            tile = board.tiles[row, col]
            if tile is not None:
                tile_lookup[id(tile)] = (col, row)

    coords: set[Coord] = set()
    for river in getattr(board, "rivers", ()) or ():
        left, right = river.getTiles()
        left_coord = tile_lookup.get(id(left))
        right_coord = tile_lookup.get(id(right))
        if left_coord is not None:
            coords.add(left_coord)
        if right_coord is not None:
            coords.add(right_coord)
    return coords


class Predicates:
    @staticmethod
    def is_land() -> TilePredicate:
        blocked = {"ocean", "coast", "lake", "mountains", "wonder", "reef"}

        def _predicate(board, coord: Coord) -> bool:
            tile = _get_tile(board, coord)
            return tile is not None and getattr(tile, "terrain", None) not in blocked

        return _Predicate("is_land", _predicate)

    @staticmethod
    def is_walkable_district() -> TilePredicate:
        blocked = {"ocean", "coast", "lake", "mountains", "wonder", "reef"}

        def _predicate(board, coord: Coord) -> bool:
            tile = _get_tile(board, coord)
            if tile is None:
                return False
            if getattr(tile, "terrain", None) in blocked:
                return False
            contains = getattr(tile, "contains", None)
            return getattr(contains, "kind", None) is None

        return _Predicate("is_walkable_district", _predicate)

    @staticmethod
    def is_valid_city_center() -> TilePredicate:
        walkable = Predicates.is_walkable_district()
        return _Predicate("is_valid_city_center", lambda board, coord: walkable(board, coord))

    @staticmethod
    def is_coast() -> TilePredicate:
        water = {"coast", "ocean", "lake"}

        def _predicate(board, coord: Coord) -> bool:
            tile = _get_tile(board, coord)
            if tile is None:
                return False
            terrain = getattr(tile, "terrain", None)
            if terrain == "coast":
                return True
            return any(
                (_get_tile(board, neighbour) is not None)
                and getattr(_get_tile(board, neighbour), "terrain", None) in water
                for neighbour in neighbours(coord)
            )

        return _Predicate("is_coast", _predicate)

    @staticmethod
    def is_river_lake_or_mountain_adjacent() -> TilePredicate:
        def _predicate(board, coord: Coord) -> bool:
            tile = _get_tile(board, coord)
            if tile is None:
                return False
            if coord in _river_endpoint_coords(board):
                return True
            for neighbour in neighbours(coord):
                neighbour_tile = _get_tile(board, neighbour)
                terrain = getattr(neighbour_tile, "terrain", None) if neighbour_tile is not None else None
                if neighbour in _river_endpoint_coords(board) or terrain in {"lake", "mountains"}:
                    return True
            return False

        return _Predicate("is_river_lake_or_mountain_adjacent", _predicate)

    @staticmethod
    def AND(*predicates: TilePredicate) -> TilePredicate:
        name = " AND ".join(predicate.name for predicate in predicates)
        return _Predicate(name, lambda board, coord: all(predicate(board, coord) for predicate in predicates))

    @staticmethod
    def OR(*predicates: TilePredicate) -> TilePredicate:
        name = " OR ".join(predicate.name for predicate in predicates)
        return _Predicate(name, lambda board, coord: any(predicate(board, coord) for predicate in predicates))

    @staticmethod
    def NOT(predicate: TilePredicate) -> TilePredicate:
        return _Predicate(f"NOT({predicate.name})", lambda board, coord: not predicate(board, coord))


_CENTER = (Predicates.is_valid_city_center(),)
_DISTRICT = (Predicates.is_walkable_district(),)
_AQUEDUCT = (
    Predicates.AND(
        Predicates.is_walkable_district(),
        Predicates.is_river_lake_or_mountain_adjacent(),
    ),
)
_HARBOR = (
    Predicates.AND(
        Predicates.is_walkable_district(),
        Predicates.is_coast(),
    ),
)


TRIANGLE_3 = Template(
    name="triangle_3",
    n_cities=3,
    expected_score=TRIANGLE_3_TARGET,
    notes="Three-city inward triangle from the module spec.",
    slots=(
        TemplateSlot((-4, 0), "city_center", 0, _CENTER),
        TemplateSlot((-2, 2), "hansa", 0, _DISTRICT),
        TemplateSlot((-4, 2), "commhub", 0, _DISTRICT),
        TemplateSlot((-3, 1), "aqueduct", 0, _AQUEDUCT),
        TemplateSlot((-3, 3), "harbor", 0, _HARBOR, optional=True),
        TemplateSlot((4, 0), "city_center", 1, _CENTER),
        TemplateSlot((1, 1), "hansa", 1, _DISTRICT),
        TemplateSlot((-1, 1), "commhub", 1, _DISTRICT),
        TemplateSlot((2, 0), "aqueduct", 1, _AQUEDUCT),
        TemplateSlot((3, 1), "harbor", 1, _HARBOR, optional=True),
        TemplateSlot((0, 4), "city_center", 2, _CENTER),
        TemplateSlot((0, 2), "hansa", 2, _DISTRICT),
        TemplateSlot((2, 2), "commhub", 2, _DISTRICT),
        TemplateSlot((-1, 3), "aqueduct", 2, _AQUEDUCT),
        TemplateSlot((1, 3), "harbor", 2, _HARBOR, optional=True),
    ),
)


DOUBLE_2 = Template(
    name="double_2",
    n_cities=2,
    expected_score=DOUBLE_2_TARGET,
    notes="Two-city shared-interior double from the module spec.",
    slots=(
        TemplateSlot((0, 0), "city_center", 0, _CENTER),
        TemplateSlot((2, 0), "hansa", 0, _DISTRICT),
        TemplateSlot((3, -1), "commhub", 0, _DISTRICT),
        TemplateSlot((1, -1), "aqueduct", 0, _AQUEDUCT),
        TemplateSlot((1, 1), "harbor", 0, _HARBOR, optional=True),
        TemplateSlot((8, 0), "city_center", 1, _CENTER),
        TemplateSlot((4, 0), "hansa", 1, _DISTRICT),
        TemplateSlot((3, 1), "commhub", 1, _DISTRICT),
        TemplateSlot((6, 0), "aqueduct", 1, _AQUEDUCT),
        TemplateSlot((5, 1), "harbor", 1, _HARBOR, optional=True),
    ),
)


COMPOSITE_2_PLUS_2 = CompositeTemplate(
    name="double_2+double_2",
    n_cities=4,
    slots=(),
    expected_score=DOUBLE_2_TARGET * 2,
    notes="Two independent doubles for N=3 (start hosted by one double, the other placed freely).",
    parts=(DOUBLE_2, DOUBLE_2),
)


COMPOSITE_3_PLUS_2 = CompositeTemplate(
    name="triangle_3+double_2",
    n_cities=5,
    slots=(),
    expected_score=COMPOSITE_5_TARGET,
    notes="Independent triangle plus double composite.",
    parts=(TRIANGLE_3, DOUBLE_2),
)


COMPOSITE_3_PLUS_3 = CompositeTemplate(
    name="triangle_3+triangle_3",
    n_cities=6,
    slots=(),
    expected_score=TRIANGLE_3_TARGET * 2,
    notes="Two independent triangles for N=5 (start hosted by one triangle, the other placed freely).",
    parts=(TRIANGLE_3, TRIANGLE_3),
)


def load_default_library() -> TemplateLibrary:
    return TemplateLibrary(
        (
            TRIANGLE_3,
            DOUBLE_2,
            COMPOSITE_2_PLUS_2,
            COMPOSITE_3_PLUS_2,
            COMPOSITE_3_PLUS_3,
        )
    )
