from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .hex import Coord, add, distance, mirror_offset, rotate_offset, sub
from .score import build_district_index, build_resource_index, score_hansa, score_total
from .templates import (
    CLUSTER_RADIUS,
    MIN_CITY_SPACING,
    ORIENTATIONS,
    WORKING_RADIUS,
    CompositeTemplate,
    SlotRole,
    Template,
    TemplateLibrary,
)


@dataclass(frozen=True)
class ConcreteSlot:
    coord: Coord
    role: SlotRole
    city_index: int
    optional: bool


@dataclass(frozen=True)
class TemplateInstance:
    template_name: str
    anchor: Coord
    rotation: int
    mirror: bool
    slots: Tuple[ConcreteSlot, ...]
    parts: Tuple["TemplateInstance", ...] = ()


@dataclass(frozen=True)
class CityPlacement:
    center: Coord
    hansa: Coord
    commhub: Coord
    harbor: Optional[Coord]
    aqueduct: Coord


@dataclass(frozen=True)
class Placement:
    cities: Tuple[CityPlacement, ...]
    score: int
    template_name: Optional[str]
    anchor: Optional[Coord]
    rotation: Optional[int]
    mirror: Optional[bool]
    instance: Optional[TemplateInstance]


@dataclass(frozen=True)
class StartingCity:
    center: Coord
    hansa: Optional[Coord]
    commhub: Optional[Coord]
    harbor: Optional[Coord]
    aqueduct: Optional[Coord]

    @classmethod
    def from_dict(cls, data, board) -> "StartingCity":
        if data is None:
            center = getattr(board, "starting_city_center", None)
            if center is None:
                raise ValueError("starting_city is required")
            return cls(center=center, hansa=None, commhub=None, harbor=None, aqueduct=None)
        if isinstance(data, cls):
            return data
        return cls(
            center=data["center"],
            hansa=data.get("hansa"),
            commhub=data.get("commhub"),
            harbor=data.get("harbor"),
            aqueduct=data.get("aqueduct"),
        )


def _in_bounds(board, coord: Coord) -> bool:
    col, row = coord
    rows, cols = board.tiles.shape
    return 0 <= row < rows and 0 <= col < cols


def _get_tile(board, coord: Coord):
    if not _in_bounds(board, coord):
        return None
    return board.tiles[coord[1], coord[0]]


def _iter_board_coords(board) -> Iterable[Coord]:
    rows, cols = board.tiles.shape
    for row in range(rows):
        for col in range(cols):
            if board.tiles[row, col] is not None:
                yield col, row


def _template_slots_by_city(instance: TemplateInstance) -> Dict[int, Dict[str, Coord]]:
    grouped: Dict[int, Dict[str, Coord]] = {}
    for slot in instance.slots:
        grouped.setdefault(slot.city_index, {})[slot.role] = slot.coord
    return grouped


def _occupied_starting_tiles(starting_city: StartingCity) -> set[Coord]:
    occupied = {starting_city.center}
    for coord in (
        starting_city.hansa,
        starting_city.commhub,
        starting_city.harbor,
        starting_city.aqueduct,
    ):
        if coord is not None:
            occupied.add(coord)
    return occupied


def enumerate_anchors(board, template: Template, starting_city: StartingCity) -> Iterable[Coord]:
    del template
    del starting_city
    yield from _iter_board_coords(board)


def enumerate_orientations() -> Iterable[Tuple[int, bool]]:
    for rotation in range(ORIENTATIONS // 2):
        yield rotation, False
        yield rotation, True


def _transform(offset: Coord, rotation: int, mirror: bool) -> Coord:
    if mirror:
        offset = mirror_offset(offset)
    return rotate_offset(offset, rotation)


def instantiate(template, anchor, rotation, mirror) -> TemplateInstance:
    if getattr(template, "parts", ()):
        return TemplateInstance(
            template_name=template.name,
            anchor=anchor,
            rotation=rotation,
            mirror=mirror,
            slots=(),
            parts=(),
        )

    slots = tuple(
        ConcreteSlot(
            coord=add(anchor, _transform(slot.offset, rotation, mirror)),
            role=slot.role,
            city_index=slot.city_index,
            optional=slot.optional,
        )
        for slot in template.slots
    )
    return TemplateInstance(
        template_name=template.name,
        anchor=anchor,
        rotation=rotation,
        mirror=mirror,
        slots=slots,
    )


def _normalize_instance(board, template: Optional[Template], instance: TemplateInstance, starting_city: StartingCity) -> Optional[TemplateInstance]:
    if template is not None and getattr(template, "parts", ()):
        return instance

    occupied_start = _occupied_starting_tiles(starting_city)
    filtered: List[ConcreteSlot] = []

    slot_defs = template.slots if template is not None else (None,) * len(instance.slots)
    for slot_def, slot in zip(slot_defs, instance.slots):
        tile = _get_tile(board, slot.coord)
        if tile is None:
            if slot.optional:
                continue
            return None
        if slot.coord in occupied_start:
            return None
        predicates = () if slot_def is None else slot_def.predicates
        if slot.optional and not all(predicate(board, slot.coord) for predicate in predicates):
            continue
        if not slot.optional and not all(predicate(board, slot.coord) for predicate in predicates):
            return None
        filtered.append(slot)

    coords = [slot.coord for slot in filtered]
    if len(coords) != len(set(coords)):
        return None

    grouped = _template_slots_by_city(
        TemplateInstance(
            template_name=instance.template_name,
            anchor=instance.anchor,
            rotation=instance.rotation,
            mirror=instance.mirror,
            slots=tuple(filtered),
            parts=instance.parts,
        )
    )

    expected_cities = template.n_cities if template is not None else len(grouped)
    if len(grouped) != expected_cities:
        return None

    for city_index, role_map in grouped.items():
        del city_index
        for required in ("city_center", "hansa", "commhub", "aqueduct"):
            if required not in role_map:
                return None
        center = role_map["city_center"]
        hansa = role_map["hansa"]
        commhub = role_map["commhub"]
        aqueduct = role_map["aqueduct"]
        if distance(center, starting_city.center) < MIN_CITY_SPACING:
            return None
        if distance(hansa, center) > WORKING_RADIUS:
            return None
        if distance(commhub, center) > WORKING_RADIUS:
            return None
        if distance(aqueduct, center) > WORKING_RADIUS:
            return None
        if "harbor" in role_map and distance(role_map["harbor"], center) > WORKING_RADIUS:
            return None
        if distance(aqueduct, center) != 1:
            return None
        if distance(aqueduct, hansa) != 1:
            return None
        if distance(commhub, hansa) != 1:
            return None

    centers = [roles["city_center"] for roles in grouped.values()]
    for index, left in enumerate(centers):
        for right in centers[index + 1:]:
            if distance(left, right) < MIN_CITY_SPACING:
                return None

    return TemplateInstance(
        template_name=instance.template_name,
        anchor=instance.anchor,
        rotation=instance.rotation,
        mirror=instance.mirror,
        slots=tuple(filtered),
        parts=instance.parts,
    )


def validate(board, instance, starting_city) -> bool:
    return _normalize_instance(board, None, instance, StartingCity.from_dict(starting_city, board)) is not None


def _build_placement(instance: TemplateInstance, score: int) -> Placement:
    grouped = _template_slots_by_city(instance)
    cities: List[CityPlacement] = []
    for city_index in sorted(grouped):
        role_map = grouped[city_index]
        cities.append(
            CityPlacement(
                center=role_map["city_center"],
                hansa=role_map["hansa"],
                commhub=role_map["commhub"],
                harbor=role_map.get("harbor"),
                aqueduct=role_map["aqueduct"],
            )
        )
    return Placement(
        cities=tuple(cities),
        score=score,
        template_name=instance.template_name,
        anchor=instance.anchor,
        rotation=instance.rotation,
        mirror=instance.mirror,
        instance=instance,
    )


def score_instance(board, instance, starting_city) -> int:
    placement = _build_placement(instance, 0)
    return score_total(
        board,
        placement,
        resource_index=build_resource_index(board),
        starting_city=starting_city,
    )


def _placement_per_city_scores(board, placement: Placement, starting_city: StartingCity) -> List[int]:
    resource_index = build_resource_index(board)
    district_index = build_district_index(placement, starting_city, board)
    return [
        score_hansa(board, city.hansa, district_index, resource_index).total
        for city in placement.cities
    ]


def _placement_key(board, placement: Placement, starting_city: StartingCity) -> Tuple[int, int, float]:
    per_city = _placement_per_city_scores(board, placement, starting_city)
    aqueduct_count = sum(
        1 for city in placement.cities if distance(city.aqueduct, city.hansa) == 1
    )
    if not per_city:
        variance = 0.0
    else:
        mean = sum(per_city) / len(per_city)
        variance = sum((score - mean) ** 2 for score in per_city) / len(per_city)
    return placement.score, aqueduct_count, -variance


def _all_template_placements(board, template: Template, starting_city: StartingCity) -> List[Placement]:
    placements: List[Placement] = []
    for anchor in enumerate_anchors(board, template, starting_city):
        for rotation, mirror in enumerate_orientations():
            raw_instance = instantiate(template, anchor, rotation, mirror)
            instance = _normalize_instance(board, template, raw_instance, starting_city)
            if instance is None:
                continue
            score = score_instance(board, instance, starting_city)
            placements.append(_build_placement(instance, score))
    return placements


def _reduce_template(template: Template, fixed_city_index: int) -> Template:
    index_map: Dict[int, int] = {}
    reduced_slots = []
    next_index = 0

    for slot in template.slots:
        if slot.city_index == fixed_city_index:
            continue
        if slot.city_index not in index_map:
            index_map[slot.city_index] = next_index
            next_index += 1
        reduced_slots.append(
            type(slot)(
                offset=slot.offset,
                role=slot.role,
                city_index=index_map[slot.city_index],
                predicates=slot.predicates,
                optional=slot.optional,
            )
        )

    return Template(
        name=template.name,
        n_cities=template.n_cities - 1,
        slots=tuple(reduced_slots),
        expected_score=template.expected_score,
        notes=template.notes,
    )


def _reduce_instance(instance: TemplateInstance, fixed_city_index: int) -> TemplateInstance:
    index_map: Dict[int, int] = {}
    reduced_slots: List[ConcreteSlot] = []
    next_index = 0

    for slot in instance.slots:
        if slot.city_index == fixed_city_index:
            continue
        if slot.city_index not in index_map:
            index_map[slot.city_index] = next_index
            next_index += 1
        reduced_slots.append(
            ConcreteSlot(
                coord=slot.coord,
                role=slot.role,
                city_index=index_map[slot.city_index],
                optional=slot.optional,
            )
        )

    return TemplateInstance(
        template_name=instance.template_name,
        anchor=instance.anchor,
        rotation=instance.rotation,
        mirror=instance.mirror,
        slots=tuple(reduced_slots),
        parts=instance.parts,
    )


def _starting_city_matches_template_city(
    instance: TemplateInstance,
    fixed_city_index: int,
    starting_city: StartingCity,
) -> bool:
    role_map = {
        slot.role: slot.coord
        for slot in instance.slots
        if slot.city_index == fixed_city_index
    }
    if role_map.get("city_center") != starting_city.center:
        return False
    for role, expected in (
        ("hansa", starting_city.hansa),
        ("commhub", starting_city.commhub),
        ("harbor", starting_city.harbor),
        ("aqueduct", starting_city.aqueduct),
    ):
        if expected is not None and role_map.get(role) != expected:
            return False
    return True


def _all_template_placements_with_start(board, template: Template, starting_city: StartingCity) -> List[Placement]:
    placements: List[Placement] = []
    center_slots = [slot for slot in template.slots if slot.role == "city_center"]

    for center_slot in center_slots:
        reduced_template = _reduce_template(template, center_slot.city_index)
        for rotation, mirror in enumerate_orientations():
            anchor = sub(starting_city.center, _transform(center_slot.offset, rotation, mirror))
            raw_instance = instantiate(template, anchor, rotation, mirror)
            if not _starting_city_matches_template_city(raw_instance, center_slot.city_index, starting_city):
                continue
            reduced_instance = _reduce_instance(raw_instance, center_slot.city_index)
            instance = _normalize_instance(board, reduced_template, reduced_instance, starting_city)
            if instance is None:
                continue
            score = score_instance(board, instance, starting_city)
            placements.append(_build_placement(instance, score))

    return placements


def _placements_conflict(left: Placement, right: Placement) -> bool:
    left_centers = [city.center for city in left.cities]
    right_centers = [city.center for city in right.cities]
    for l_center in left_centers:
        for r_center in right_centers:
            if distance(l_center, r_center) <= CLUSTER_RADIUS:
                return True
    left_tiles = {
        coord
        for city in left.cities
        for coord in (city.center, city.hansa, city.commhub, city.harbor, city.aqueduct)
        if coord is not None
    }
    right_tiles = {
        coord
        for city in right.cities
        for coord in (city.center, city.hansa, city.commhub, city.harbor, city.aqueduct)
        if coord is not None
    }
    return bool(left_tiles & right_tiles)


def _fit_composite_template(board, template: CompositeTemplate, starting_city: StartingCity) -> Optional[Placement]:
    part_placements = [_all_template_placements(board, part, starting_city) for part in template.parts]
    if not part_placements or any(not placements for placements in part_placements):
        return None

    best: Optional[Placement] = None
    for left in part_placements[0]:
        for right in part_placements[1]:
            if _placements_conflict(left, right):
                continue
            instance = TemplateInstance(
                template_name=template.name,
                anchor=(0, 0),
                rotation=0,
                mirror=False,
                slots=(),
                parts=(left.instance, right.instance) if left.instance and right.instance else (),
            )
            placement = Placement(
                cities=left.cities + right.cities,
                score=left.score + right.score,
                template_name=template.name,
                anchor=None,
                rotation=None,
                mirror=None,
                instance=instance,
            )
            if best is None or _placement_key(board, placement, starting_city) > _placement_key(board, best, starting_city):
                best = placement
    return best


def _fit_composite_template_with_start(
    board,
    template: CompositeTemplate,
    starting_city: StartingCity,
) -> Optional[Placement]:
    if len(template.parts) != 2:
        return None

    best: Optional[Placement] = None
    for host_index in range(len(template.parts)):
        host_part = template.parts[host_index]
        other_part = template.parts[1 - host_index]
        host_placements = _all_template_placements_with_start(board, host_part, starting_city)
        other_placements = _all_template_placements(board, other_part, starting_city)
        if not host_placements or not other_placements:
            continue

        for host in host_placements:
            for other in other_placements:
                if _placements_conflict(host, other):
                    continue
                instance = TemplateInstance(
                    template_name=template.name,
                    anchor=(0, 0),
                    rotation=0,
                    mirror=False,
                    slots=(),
                    parts=tuple(
                        part_instance
                        for part_instance in (host.instance, other.instance)
                        if part_instance is not None
                    ),
                )
                placement = Placement(
                    cities=host.cities + other.cities,
                    score=host.score + other.score,
                    template_name=template.name,
                    anchor=None,
                    rotation=None,
                    mirror=None,
                    instance=instance,
                )
                if best is None or _placement_key(board, placement, starting_city) > _placement_key(board, best, starting_city):
                    best = placement

    return best


def _fit_template_with_start(board, template, starting_city) -> Optional[Placement]:
    sc = StartingCity.from_dict(starting_city, board)
    if getattr(template, "parts", ()):
        return _fit_composite_template_with_start(board, template, sc)

    best: Optional[Placement] = None
    for placement in _all_template_placements_with_start(board, template, sc):
        if best is None or _placement_key(board, placement, sc) > _placement_key(board, best, sc):
            best = placement
    return best


def fit_template(board, template, starting_city) -> Optional[Placement]:
    sc = StartingCity.from_dict(starting_city, board)
    if getattr(template, "parts", ()):
        return _fit_composite_template(board, template, sc)

    best: Optional[Placement] = None
    for placement in _all_template_placements(board, template, sc):
        if best is None or _placement_key(board, placement, sc) > _placement_key(board, best, sc):
            best = placement
    return best


def fit_best(board, library, starting_city, n) -> Optional[Placement]:
    sc = StartingCity.from_dict(starting_city, board)
    total_cities = n + 1
    best: Optional[Placement] = None
    for template in library.for_n(total_cities):
        placement = _fit_template_with_start(board, template, sc)
        if placement is None:
            continue
        if best is None or _placement_key(board, placement, sc) > _placement_key(board, best, sc):
            best = placement
    return best
