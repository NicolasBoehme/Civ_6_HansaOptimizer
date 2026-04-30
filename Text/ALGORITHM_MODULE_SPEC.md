ex# Hansa Optimizer — Algorithm Module Specification

Last updated: 2026-04-30
Status: Draft — pre-implementation
Companion to: `REQUIREMENTS_REDO.md`

---

## 0. How To Use This Doc

This document is the **implementation contract** for the rebuilt `algorithm/` package described in `REQUIREMENTS_REDO.md`. It is structured so each module section is **self-contained** and can be handed to a different AI / human worker without context bleed. Workers should only need:

- This doc
- `REQUIREMENTS_REDO.md` (the *what / why*)
- `Tile Logic/` source (`Tile.py`, `Board.py`, `River.py`) — read-only dependency
- `test_board.py`, `main.py`, `visualizer.py` — read-only consumers

A worker assigned **module M** must not modify any module other than M. Cross-module changes are coordinated by the integrator.

Each module section follows the same template:

> **0.** Owner role · **1.** File path · **2.** Allowed imports · **3.** Public exports · **4.** Data structures · **5.** Functions · **6.** Behavior contract · **7.** Acceptance tests · **8.** Notes / gotchas

---

## 1. Architecture Overview

### 1.1 Module dependency graph

```
                          ┌──────────────┐
                          │ Tile Logic/  │  (external, read-only)
                          │  Board, Tile │
                          │  River       │
                          └──────┬───────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
   ┌──────▼──────┐        ┌──────▼──────┐        ┌──────▼──────┐
   │   hex.py    │        │  score.py   │        │ predicates  │
   │ (geometry)  │◄───────┤ (scoring)   │        │  (in        │
   └──────┬──────┘        └──────┬──────┘        │ templates)  │
          │                      │                └──────┬──────┘
          │                      │                       │
          │                ┌─────┴────────┐              │
          │                │              │              │
   ┌──────▼──────┐  ┌──────▼──────┐ ┌─────▼──────────────▼──┐
   │ fallback.py │  │  fit.py     │ │     templates.py      │
   │             │  │             │ │  (data + library)     │
   └──────┬──────┘  └──────┬──────┘ └───────────┬───────────┘
          │                │                    │
          └────────┬───────┴────────────────────┘
                   │
            ┌──────▼──────┐
            │  solve.py   │   ← public entry point
            └──────┬──────┘
                   │
            ┌──────▼──────┐
            │ __init__.py │   ← re-exports for main.py / visualizer.py
            └─────────────┘
```

**Build order** (topological, for parallel AI assignment):
1. **Tier 0 (no algorithm deps):** `hex.py`, `score.py`
2. **Tier 1:** `templates.py` (uses `hex`, `score` for offset math + canonical scores)
3. **Tier 2:** `fit.py` (uses `hex`, `score`, `templates`), `fallback.py` (uses `hex`, `score`)
4. **Tier 3:** `solve.py` (uses `fit`, `fallback`, `templates`)
5. **Tier 4:** `__init__.py` (re-exports)

Workers on tiers ≥ 1 can stub Tier-0 modules from this spec while waiting for them to land.

### 1.2 Canonical empirical targets

These numbers drive both template baseline scores and acceptance tests. They are the user's empirical findings, encoded once here so every module can reference them.

| Symbol | Value | Meaning |
|---|---|---|
| `TRIANGLE_3_TARGET` | **33** | Combined Hansa production for the 3-city triangle template on neutral terrain, no resources. |
| `DOUBLE_2_TARGET` | **15** | Combined Hansa production for the 2-city double template, neutral terrain (8 + 7 split). |
| `COMPOSITE_5_TARGET` | **48** | `TRIANGLE_3_TARGET + DOUBLE_2_TARGET` for the N=5 composite. |
| `PER_HANSA_MAX_TRIANGLE_3` | **11** | Highest single-Hansa score expected inside `triangle_3`. |
| `MIN_CITY_SPACING` | **4** | Hex distance — minimum allowed between any two city centers (Civ 6 standard). |
| `WORKING_RADIUS` | **3** | Hex distance — districts must be within this from their city center. |
| `CLUSTER_RADIUS` | **6** | Hex distance — beyond this, two cities cannot share district adjacency. |
| `ORIENTATIONS` | **12** | 6 rotations × 2 mirrors. Used by `fit.py` for anchor sweeps. |

> **NB:** All numerical claims above are **assumptions** to be confirmed by the user. They are referenced from acceptance tests so a single change here propagates correctly.

### 1.3 Shared coordinate convention

- All coordinates are **double-width hex** `(col, row)` — same as the existing `Board`.
- `Coord = Tuple[int, int]`.
- Six neighbour offsets (canonical order — used by `hex.py` and template rotation):
  ```
  E   = ( 2,  0)
  W   = (-2,  0)
  NE  = ( 1, -1)
  NW  = (-1, -1)
  SE  = ( 1,  1)
  SW  = (-1,  1)
  ```
  Rotation index `k ∈ {0..5}` rotates the offset list by `k` positions in the order `[E, NE, NW, W, SW, SE]` (counter-clockwise 60° per step).

### 1.4 District kind constants

Defined once in `__init__.py` and re-exported from every module that uses them:

```python
H  = "hansa"
CH = "commhub"
HB = "harbor"
AQ = "aqueduct"
OTHER = "other"
DistrictKind = Literal["hansa", "commhub", "harbor", "aqueduct", "other"]
```

These match `Tile Logic/Tile.py::District.*` exactly. Do **not** rename.

---

## 2. Module: `algorithm/hex.py`

**Owner role:** `hex-worker`

### 2.1 File path

`/algorithm/hex.py`

### 2.2 Allowed imports

- `typing`
- *(none from `algorithm/`)*
- *(no Tile-Logic imports)*

This module is pure math. It must not import `Board`, `Tile`, or `River`.

### 2.3 Public exports

```python
Coord                            # type alias = Tuple[int, int]
NEIGHBOUR_OFFSETS                # tuple of 6 (dcol, drow)
neighbours(c)                    # -> list[Coord]
distance(a, b)                   # -> int
tiles_within_radius(center, r)   # -> set[Coord]
rotate_offset(offset, k)         # -> Coord
mirror_offset(offset)            # -> Coord
rotate_offsets(offsets, k, mirror=False)  # -> list[Coord]
add(a, b)                        # -> Coord  (vector add)
sub(a, b)                        # -> Coord
```

### 2.4 Data structures

```python
Coord = Tuple[int, int]

NEIGHBOUR_OFFSETS: Tuple[Coord, ...] = (
    ( 2,  0), ( 1, -1), (-1, -1),
    (-2,  0), (-1,  1), ( 1,  1),
)
# Order matters: index k corresponds to a 60° CCW rotation step.
```

### 2.5 Functions

| Function | Signature | Behavior |
|---|---|---|
| `neighbours` | `(c: Coord) -> list[Coord]` | Returns the 6 doubled-coord neighbours of `c`, in `NEIGHBOUR_OFFSETS` order. No bounds checking — caller filters. |
| `distance` | `(a: Coord, b: Coord) -> int` | Hex distance via cube conversion. `(col,row) -> (x=(col-row)/2, z=row, y=-x-z)`. Distance = `(|dx|+|dy|+|dz|)/2`. |
| `tiles_within_radius` | `(center: Coord, r: int) -> set[Coord]` | All `Coord`s with `distance(center, c) <= r`. Includes `center`. |
| `rotate_offset` | `(offset: Coord, k: int) -> Coord` | Rotate a `(dcol, drow)` offset around origin by `k * 60°` CCW, `k mod 6`. Implemented by cube rotation: `(x, y, z) -> (-z, -x, -y)` per step. |
| `mirror_offset` | `(offset: Coord) -> Coord` | Reflect across the q-axis: cube `(x, y, z) -> (x, z, y)`. Equivalent to `(dcol, drow) -> (dcol, -drow)` followed by re-canonicalisation if needed. |
| `rotate_offsets` | `(offsets: Iterable[Coord], k: int, mirror: bool) -> list[Coord]` | Apply mirror (if true) then rotate-by-k to each offset. Used by `fit.py` to instantiate templates. |

### 2.6 Behavior contract

- `distance` is symmetric, non-negative, zero iff `a == b`, triangle inequality holds.
- `rotate_offset(o, 0) == o`. `rotate_offset(o, 6) == o`. `rotate_offset(rotate_offset(o, k), 6-k) == o`.
- `mirror_offset(mirror_offset(o)) == o`.
- For any neighbour offset `n` and any `k`: `rotate_offset(n, k)` is also a neighbour offset.

### 2.7 Acceptance tests

```python
assert distance((0,0), (2,0)) == 1
assert distance((0,0), (4,0)) == 2
assert distance((0,0), (1,1)) == 1
assert distance((0,0), (3,3)) == 3
assert len(tiles_within_radius((0,0), 0)) == 1
assert len(tiles_within_radius((0,0), 1)) == 7
assert len(tiles_within_radius((0,0), 2)) == 19
assert len(tiles_within_radius((0,0), 3)) == 37
assert set(rotate_offsets(NEIGHBOUR_OFFSETS, k=1)) == set(NEIGHBOUR_OFFSETS)
assert rotate_offset((2, 0), 1) == (1, -1)   # E -> NE
assert rotate_offset((2, 0), 3) == (-2, 0)   # E -> W
```

### 2.8 Notes / gotchas

- Double-width parity: `(col + row) % 2` must be constant across all valid tiles on the board (the tile grid is a doubled hex). Rotation/mirror around any valid origin preserves parity.
- Do **not** depend on the order of `tiles_within_radius` — return a `set`, callers may sort.

---

## 3. Module: `algorithm/score.py`

**Owner role:** `score-worker`

### 3.1 File path

`/algorithm/score.py`

### 3.2 Allowed imports

- `typing`, `dataclasses`
- `algorithm.hex` — `Coord`, `neighbours`
- *Read-only access to `Tile`/`District`/`Resource` shapes via duck typing on `tile.terrain` and `tile.contains`. Do not `import Tile`.*

### 3.3 Public exports

```python
DistrictKind                       # str literal
H, CH, HB, AQ, OTHER               # mirrored constants (also in __init__.py)
ResourceTier                       # str literal
HansaScoreBreakdown                # dataclass
score_hansa(board, hansa_coord, district_index, resource_index) -> HansaScoreBreakdown
score_total(board, placement, *, resource_index=None) -> int
build_district_index(placement, starting_city) -> dict[Coord, DistrictKind]
build_resource_index(board) -> dict[Coord, ResourceTier]
```

### 3.4 Data structures

```python
@dataclass(frozen=True)
class HansaScoreBreakdown:
    commhub:    int  # +2 each adjacent CH
    harbor:     int  # +2 each adjacent HB
    aqueduct:   int  # +2 each adjacent AQ
    other:      int  # +1 each adjacent OTHER (incl. other cities' Hansas)
    luxury:     int  # +2 each adjacent luxury/strategic resource
    bonus:      int  # +1 each adjacent bonus resource

    @property
    def total(self) -> int:
        return self.commhub + self.harbor + self.aqueduct + self.other + self.luxury + self.bonus
```

### 3.5 Functions

| Function | Signature | Behavior |
|---|---|---|
| `build_district_index` | `(placement: Placement, starting_city: dict | StartingCity) -> dict[Coord, DistrictKind]` | Flatten every district tile (Hansa/CH/HB/AQ + the starting city's pre-existing districts) into a `Coord -> DistrictKind` lookup. Hansa-Hansa adjacency must show up as `OTHER`-style +1 (per Benefit Matrix). Implementation hint: treat any *other-city Hansa* and any *other district kind* the way the table dictates — a Hansa adjacent to another Hansa contributes `+1` (the `OTHER` slot), not `+2`. |
| `build_resource_index` | `(board) -> dict[Coord, ResourceTier]` | Walk `board.tiles`. For tiles whose `tile.contains` is a `Resource`, record `tier ∈ {"bonus", "luxury", "strategic"}`. |
| `score_hansa` | `(board, hansa_coord, district_index, resource_index) -> HansaScoreBreakdown` | For each of the 6 neighbours of `hansa_coord`, increment the matching field. Skip out-of-bounds neighbours (where `board.tiles[r,c] is None`). |
| `score_total` | `(board, placement, *, resource_index=None) -> int` | Sum `score_hansa(...).total` for every Hansa in `placement.cities`. The starting city's own Hansa is **not** counted (it is fixed and not optimised). |

### 3.6 Behavior contract

- This module is **Hansa-only**. Per `REQUIREMENTS_REDO.md` §2, do not score CH/HB gold, do not score river-on-CH, do not score worked tiles.
- Bonus stacks: a tile that is *both* a luxury resource and an other-city CH counts in **both** rows (the Civ rule: adjacency bonuses stack across categories).
- Aqueduct→Hansa is asymmetric (+2 to Hansa, 0 back). Only the Hansa side is scored here.

### 3.7 Acceptance tests

- A Hansa with a CommHub on each of its 6 neighbours scores `+12` (`commhub=12`).
- A Hansa with one CH, one Harbor, one AQ adjacent (district triangle) scores `+6`.
- A Hansa adjacent to another Hansa scores `+1` (other), **not** `+2` — guards against the common bug of double-counting Hansas as CH-tier.
- A Hansa adjacent to a luxury resource and a CH on the same tile is **invalid input** (one district per tile rule); module may assert. A luxury *next to* a CH (different tiles) gives `+2 (lux) + 2 (commhub) = +4`.
- `score_total` on the canonical `triangle_3` placement (provided as a fixture from `templates.py`) returns exactly `TRIANGLE_3_TARGET`.

### 3.8 Notes / gotchas

- `Tile Logic/Tile.py::District` has a `kind: str` field, not a `kind: DistrictKind`. Compare via the string constants `H`, `CH`, `HB`, `AQ`, `OTHER`.
- `Resource.tier` is `"bonus" | "luxury" | "strategic"`. Map `luxury` and `strategic` to the `luxury` field of `HansaScoreBreakdown` (per brief §2: luxury and strategic both give +2).
- Out-of-bounds neighbours: `board.tiles[r, c]` may be `None` (the board is a sparse double-width grid). Treat as no-contribution, don't crash.

---

## 4. Module: `algorithm/templates.py`

**Owner role:** `template-worker`

### 4.1 File path

`/algorithm/templates.py`

### 4.2 Allowed imports

- `typing`, `dataclasses`
- `algorithm.hex` — `Coord`, rotation helpers
- `algorithm.score` — for the canonical-score fixture only (used in tests, not in template logic)

### 4.3 Public exports

```python
SlotRole                          # Literal "city_center" | "hansa" | "commhub" | "harbor" | "aqueduct"
TilePredicate                     # Protocol (board, coord) -> bool
Predicates                        # namespace with concrete predicate factories
TemplateSlot                      # dataclass
Template                          # dataclass
TemplateLibrary                   # frozen list-like wrapper
load_default_library()            # -> TemplateLibrary
TRIANGLE_3                        # Template
DOUBLE_2                          # Template
COMPOSITE_3_PLUS_2                # Template
```

### 4.4 Data structures

```python
SlotRole = Literal["city_center", "hansa", "commhub", "harbor", "aqueduct"]

class TilePredicate(Protocol):
    name: str
    def __call__(self, board, coord: Coord) -> bool: ...

@dataclass(frozen=True)
class TemplateSlot:
    offset:     Coord            # relative to template anchor (pre-rotation)
    role:       SlotRole
    city_index: int              # which template-city this slot belongs to (0..n_cities-1)
    predicates: tuple[TilePredicate, ...]   # all must hold for the slot to be valid
    optional:   bool = False     # e.g. Harbor: skip if not coastal, do not fail the template

@dataclass(frozen=True)
class Template:
    name:           str
    n_cities:       int
    slots:          tuple[TemplateSlot, ...]
    expected_score: int          # baseline Hansa total on neutral terrain (no resources)
    notes:          str = ""

class TemplateLibrary:
    def __init__(self, templates: Iterable[Template]): ...
    def for_n(self, n: int) -> list[Template]:
        """Return all templates that place exactly n cities."""
```

### 4.5 The Predicates namespace

Concrete `TilePredicate` factories (each returns a callable carrying a `.name`):

| Predicate | Meaning |
|---|---|
| `Predicates.is_land()` | `tile.terrain not in {"ocean", "coast", "lake", "mountains", "wonder", "reef"}` |
| `Predicates.is_walkable_district()` | land *and* not a wonder/mountain *and* `tile.contains` is not already a District |
| `Predicates.is_valid_city_center()` | `is_walkable_district()` *and* not on the starting city / its districts (caller injects this set) |
| `Predicates.is_coast()` | `tile.terrain == "coast"` *or* land tile with a coast/ocean/lake neighbour |
| `Predicates.is_river_lake_or_mountain_adjacent()` | tile has at least one neighbour that is a river-edge endpoint, lake, or mountain (used for aqueduct slots) |
| `Predicates.AND(*ps)`, `Predicates.OR(*ps)`, `Predicates.NOT(p)` | combinators |

Predicates take `(board, coord)`. They are pure, deterministic, and side-effect free.

### 4.6 The canonical templates

#### 4.6.1 `TRIANGLE_3`

Three city centers forming a tight equilateral hex triangle with the **interior tile as the anchor**. Each city's Aqueduct points inward (toward the anchor). Hansas and CommHubs are packed in the interior so each Hansa is adjacent to other-city CHs and AQs.

Coordinate sketch (anchor `A = (0,0)`; offsets in double-width):

```
                  C0 = (-2, -2)
                       \
                        AQ0 = (-1, -1)
                        /
              H0 = (0, -2)   CH0 = (-2,  0)
                              ...
              C1 = ( 4, -2)        C2 = ( 0,  4)
              AQ1 = ( 3, -1)       AQ2 = ( 1,  3)
              H1 = ( 2, -2)        H2 = ( 0,  2)
              CH1 = ( 4,  0)       CH2 = (-2,  2)
```

> **Concrete offsets are TBD by the integrator** once a saved board is supplied (see `REQUIREMENTS_REDO.md` §7). The above is the *shape intent* — three centers, three inward-pointing aqueducts, three Hansas + CHs near the anchor. The data file is the single source of truth; this doc only fixes `n_cities = 3`, `expected_score = TRIANGLE_3_TARGET = 33`, and the **adjacency invariants** below.

**Invariants every concrete `TRIANGLE_3` instance must satisfy** (verified by a unit test on the offset table itself):

1. `n_cities == 3`.
2. Each city has exactly one slot of each role except Harbor (which is optional).
3. For each city `i`: `distance(C_i, AQ_i) == 1`.
4. For each city `i`: `distance(H_i, CH_i) == 1` and `distance(H_i, AQ_i) == 1` (district triangle).
5. For each city `i`: `distance(H_i, C_i) <= WORKING_RADIUS` (and same for CH/AQ).
6. For each pair `i ≠ j`: `distance(C_i, C_j) >= MIN_CITY_SPACING`.
7. At least one Hansa has `distance(H_i, H_j) >= 2` for all `j ≠ i` (Hansas should not cluster on each other when hubs are available — soft-encoded as: no two Hansas are direct neighbours in the canonical layout).
8. Scoring this offset table on a flat plains board with no resources via `score.score_total` yields `TRIANGLE_3_TARGET`.

#### 4.6.2 `DOUBLE_2`

Two city centers placed at the spacing that maximises the count of districts that can sit on tiles adjacent to *both* cities' working radii — the "8 + 7" arrangement.

```
n_cities = 2
expected_score = DOUBLE_2_TARGET = 15      (8 + 7 split — H0 yields 8, H1 yields 7)
```

Same invariants 2–6 as above, and:
- `distance(C0, C1) == MIN_CITY_SPACING` (they sit at exactly the minimum legal spacing).
- The Hansas of the two cities **share at least one common neighbour** (a CH belonging to one city that is adjacent to both Hansas).

#### 4.6.3 `COMPOSITE_3_PLUS_2`

Composite = `TRIANGLE_3` placed at one anchor, plus `DOUBLE_2` placed at a second anchor far enough away to be **non-interacting** (`distance(any_C_in_triangle, any_C_in_double) > CLUSTER_RADIUS`). When both fit, the composite scores `TRIANGLE_3_TARGET + DOUBLE_2_TARGET = COMPOSITE_5_TARGET`.

Implementation: `COMPOSITE_3_PLUS_2` is **not** a flat slot list — it's a thin wrapper:

```python
@dataclass(frozen=True)
class CompositeTemplate(Template):
    parts: tuple[Template, ...]    # (TRIANGLE_3, DOUBLE_2)
```

`fit.py` recognises the composite and fits each part as an independent sub-problem with its own anchor sweep; the validity check additionally enforces non-interaction.

### 4.7 `load_default_library()`

Returns a `TemplateLibrary([TRIANGLE_3, DOUBLE_2, COMPOSITE_3_PLUS_2])`. Future templates added by appending here.

### 4.8 Behavior contract

- All offsets are **frozen** at module load. Templates are immutable.
- `expected_score` is the value `score.score_total` returns when the template is instantiated on a featureless plains board, no resources, no rivers (rivers don't affect Hansa scoring directly per `REQUIREMENTS_REDO.md`).
- Predicates are referentially transparent — same `(board, coord)` always yields the same answer in a single solve.

### 4.9 Acceptance tests

```python
lib = load_default_library()
assert {t.name for t in lib.for_n(3)} == {"triangle_3"}
assert {t.name for t in lib.for_n(2)} == {"double_2"}
assert {t.name for t in lib.for_n(5)} == {"triangle_3+double_2"}

# Invariant tests on TRIANGLE_3 offset table:
for slot in TRIANGLE_3.slots:
    if slot.role == "aqueduct":
        ci = slot.city_index
        center = next(s.offset for s in TRIANGLE_3.slots if s.role == "city_center" and s.city_index == ci)
        assert distance(slot.offset, center) == 1

# Score fixture test (uses a flat plains board):
flat_board = make_flat_plains_board(rows=15, cols=21)
placement = instantiate_on(TRIANGLE_3, flat_board, anchor=(10, 7), rotation=0, mirror=False)
assert score_total(flat_board, placement) == TRIANGLE_3_TARGET
```

### 4.10 Notes / gotchas

- The data file (offsets) is the single source of truth for *what* the template looks like. The invariants in §4.6 are *checks*, not derivations.
- Harbor slots **must** be marked `optional=True`. A non-coastal triangle is still valid; the Harbor is simply skipped. (See `REQUIREMENTS_REDO.md` §7 confirmation: "optional per-center upgrade if that center is coastal.")

---

## 5. Module: `algorithm/fit.py`

**Owner role:** `fit-worker`

### 5.1 File path

`/algorithm/fit.py`

### 5.2 Allowed imports

- `typing`, `dataclasses`
- `algorithm.hex`
- `algorithm.score` — for scoring placed templates
- `algorithm.templates` — for the library and template types

### 5.3 Public exports

```python
ConcreteSlot                 # dataclass (template slot, after rotation/mirror, mapped to absolute coord)
TemplateInstance             # dataclass (a template + anchor + orientation, with absolute coords)
CityPlacement                # dataclass (one city's resolved positions)
Placement                    # dataclass (full solver output)
StartingCity                 # dataclass (parsed/normalised starting-city input)

enumerate_anchors(board, template, starting_city) -> Iterable[Coord]
enumerate_orientations() -> Iterable[tuple[int, bool]]
instantiate(template, anchor, rotation, mirror) -> TemplateInstance
validate(board, instance, starting_city) -> bool
score_instance(board, instance, starting_city) -> int
fit_template(board, template, starting_city) -> Optional[Placement]
fit_best(board, library, starting_city, n) -> Optional[Placement]
```

### 5.4 Data structures

```python
@dataclass(frozen=True)
class ConcreteSlot:
    coord:      Coord
    role:       SlotRole
    city_index: int
    optional:   bool

@dataclass(frozen=True)
class TemplateInstance:
    template_name: str
    anchor:        Coord
    rotation:      int       # 0..5
    mirror:        bool
    slots:         tuple[ConcreteSlot, ...]      # absolute coords, post-rotation
    parts:         tuple["TemplateInstance", ...] = ()   # for composites; flat templates leave this empty

@dataclass(frozen=True)
class CityPlacement:
    center:    Coord
    hansa:     Coord
    commhub:   Coord
    harbor:    Optional[Coord]
    aqueduct:  Coord

@dataclass(frozen=True)
class Placement:
    cities:        tuple[CityPlacement, ...]
    score:         int
    template_name: Optional[str]    # None ⇒ fallback path was used
    anchor:        Optional[Coord]  # None for composite/fallback; per-part info lives in `instance`
    rotation:      Optional[int]
    mirror:        Optional[bool]
    instance:      Optional[TemplateInstance]    # full provenance, optional for fallback

@dataclass(frozen=True)
class StartingCity:
    center:    Coord
    hansa:     Optional[Coord]
    commhub:   Optional[Coord]
    harbor:    Optional[Coord]
    aqueduct:  Optional[Coord]

    @classmethod
    def from_dict(cls, d: dict | None, board) -> "StartingCity": ...
```

### 5.5 Functions

#### 5.5.1 `enumerate_anchors`

```python
def enumerate_anchors(board, template: Template, starting_city: StartingCity) -> Iterable[Coord]:
    """Yield every coord on the board that could legally serve as the anchor
    for *some* orientation of `template`. Coarse pre-filter only — the goal is
    to skip obviously-doomed anchors (off-board, inside the starting city's
    working radius). Exhaustive validity is delegated to `validate`."""
```

Coarse anchor filter:
- `coord` is on the board (`board.tiles[r,c] is not None`).
- The bounding circle of the template (`max |offset|` over slots) fits on the board around `coord`.
- Every `city_center` slot, after some orientation, ends up at distance `>= MIN_CITY_SPACING` from the starting city center. (Use the slot's *closest possible* rotation — if even that violates spacing, skip the anchor.)

#### 5.5.2 `enumerate_orientations`

Yields the 12 `(rotation, mirror)` tuples — `rotation ∈ 0..5`, `mirror ∈ {False, True}`. Defaulting to *all 12* orientations per `REQUIREMENTS_REDO.md` §7.

#### 5.5.3 `instantiate`

```python
def instantiate(template, anchor, rotation, mirror) -> TemplateInstance:
    """Apply orientation to each slot's offset, add `anchor`, build a
    TemplateInstance. For composites, recurse on `template.parts`, allowing
    each part its own (anchor, rotation, mirror) — see `fit_best` for the
    composite anchor sweep policy."""
```

For flat templates: `slot.coord = anchor + rotate_offset(mirror_offset?(slot.offset), rotation)`.

#### 5.5.4 `validate`

```python
def validate(board, instance, starting_city) -> bool:
    """Return True iff the instance is fully placeable on the current board.
    Order of checks (cheapest first):

      1. All slot coords are on the board.
      2. No two slot coords collide.
      3. No slot coord is on the starting city's center or its existing districts.
      4. For each city: distance(center_i, starting_city.center) >= MIN_CITY_SPACING
         AND for every other city j: distance(center_i, center_j) >= MIN_CITY_SPACING.
      5. For each non-center slot: distance(slot.coord, its center) <= WORKING_RADIUS.
      6. For each slot: every predicate in slot.predicates holds at slot.coord.
      7. Aqueduct gating: for each city i, the AQ slot must be adjacent to the
         Hansa slot of the same city. (Per REQ §3 / §4.3 — Hansa+AQ adjacency
         is mandatory, otherwise the city is rejected.)
      8. Composite-only: every C_i in part A is at distance > CLUSTER_RADIUS
         from every C_j in part B (parts must be non-interacting).

    Optional Harbor slots that fail predicate 6 are *removed* from the
    instance, not failed."""
```

#### 5.5.5 `score_instance`

Builds a `Placement` shape from the `TemplateInstance` + `starting_city`, then calls `score.score_total(board, placement)`. Returns the integer total.

#### 5.5.6 `fit_template`

```python
def fit_template(board, template, starting_city) -> Optional[Placement]:
    """Sweep all (anchor, rotation, mirror) combos for one template, return
    the best-scoring valid Placement, or None if nothing fits."""
```

Pseudocode:
```
best = None
for anchor in enumerate_anchors(board, template, starting_city):
    for rot, mirror in enumerate_orientations():
        inst = instantiate(template, anchor, rot, mirror)
        if not validate(board, inst, starting_city):
            continue
        s = score_instance(board, inst, starting_city)
        if best is None or s > best.score:
            best = build_placement(inst, s)
return best
```

#### 5.5.7 `fit_best`

```python
def fit_best(board, library, starting_city, n) -> Optional[Placement]:
    """For each template in library.for_n(n), call fit_template; return
    the global best.

    Tie-break (per REQ §7): when scores are equal, prefer
       (a) more aqueducts adjacent to Hansas
       (b) lower variance of per-city Hansa scores"""
```

For composite templates: do a nested anchor sweep — outer loop over part-A anchors, inner loop over part-B anchors filtered to those `> CLUSTER_RADIUS` from every part-A center. Score = sum of part scores.

### 5.6 Behavior contract

- `validate` is **the** authority on whether an instance is legal. `enumerate_anchors` may over-yield; it must not under-yield.
- `score_instance` must be deterministic and idempotent: calling it twice on the same `(board, instance, starting_city)` returns the same integer.
- A returned `Placement` always has: `len(cities) == template.n_cities` (flat) or `sum(part.n_cities for part in parts)` (composite).

### 5.7 Acceptance tests

1. On a 21×15 flat plains board with starting city far from the anchor, `fit_template(TRIANGLE_3)` returns a `Placement` with `score == TRIANGLE_3_TARGET` and a non-None `instance`.
2. On a 21×15 flat plains board, `fit_template(DOUBLE_2)` returns score `DOUBLE_2_TARGET`.
3. For N=5 with both templates fittable: `fit_best(library, starting_city, 5)` returns the composite, and `placement.score == COMPOSITE_5_TARGET`.
4. When the starting city is too close to every legal anchor, `fit_template` returns `None`.
5. Aqueduct gating: for a board where no AQ slot can find a river/lake/mountain neighbour, `validate` returns `False` for every orientation.

### 5.8 Notes / gotchas

- The "anchor" in `Placement` is the **flat-template anchor**. For composites, `Placement.anchor` is `None` and provenance lives in `instance.parts[i].anchor`.
- Tie-break (a) requires recomputing per-city aqueduct counts — keep the helper local; do not pollute `score.py`.
- 12 orientations × ~10² anchors × 5 templates is small; do not over-engineer with caching.

---

## 6. Module: `algorithm/fallback.py`

**Owner role:** `fallback-worker`

### 6.1 File path

`/algorithm/fallback.py`

### 6.2 Allowed imports

- `typing`, `dataclasses`
- `algorithm.hex`
- `algorithm.score`
- `algorithm.fit` — for `Placement`, `CityPlacement`, `StartingCity` types only (not for `fit_template`)

### 6.3 Public exports

```python
fallback_solve(board, starting_city, n) -> Placement
compute_influence_field(board, starting_city) -> dict[Coord, int]
enumerate_valid_centers(board, starting_city, already_placed) -> list[Coord]
enumerate_aqueduct_tiles(board, center) -> list[Coord]
find_district_triangle(board, center, taken) -> Optional[tuple[Coord, Coord, Coord]]
```

### 6.4 Algorithm

Greedy, sequential per-city. **No** template matching here — this module runs only when `fit_best` returns `None`.

```
placed = []
for k in range(n):
    centers = enumerate_valid_centers(board, starting_city, placed)
    candidates = []
    for c in centers:
        aqs = enumerate_aqueduct_tiles(board, c)
        if not aqs:
            continue                       # AQ-gated rejection (REQ §4.3)
        for aq in aqs:
            tri = find_district_triangle(board, c, taken=set_of_used_tiles(placed) | {aq})
            if tri is None:
                continue
            hansa, commhub, _aq = tri      # AQ already chosen; tri uses it as the third corner
            score = local_score(board, hansa, commhub, aq, placed, starting_city)
            candidates.append((score, CityPlacement(c, hansa, commhub, None, aq)))
    if not candidates:
        raise FallbackInfeasible(f"city {k+1} has no valid placement")
    _, best = max(candidates, key=lambda x: x[0])
    placed.append(best)

return Placement(cities=tuple(placed), score=score_total(...), template_name=None, ...)
```

### 6.5 Helpers

| Function | Spec |
|---|---|
| `compute_influence_field` | For each tile `t`, sum the Hansa-row Benefit-Matrix contributions of fixed elements (starting city's CH/HB/AQ + resources). Returned as `dict[Coord, int]`. Computed once per `fallback_solve` call. |
| `enumerate_valid_centers` | Tiles at `distance >= MIN_CITY_SPACING` from starting-city center *and* every center already in `placed`. Excludes water/mountain/wonder. |
| `enumerate_aqueduct_tiles` | Tiles at hex distance 1 from `center` whose neighbours include a river-edge endpoint, lake, or mountain. Returns 0–3 tiles. |
| `find_district_triangle` | Search the working radius of `center` for a triple `(H, CH, AQ)` that is mutually adjacent (each pair within distance 1) and: respects `taken`; the AQ tile is adjacent to `center`; the AQ tile is river/lake/mountain-adjacent. Returns the highest-scoring triple by local Hansa contribution, or `None`. |

### 6.6 Behavior contract

- The returned `Placement` has `template_name = None` to signal fallback.
- Sequential, not joint: when placing city `k+1`, cities `0..k` are *fixed*. This is faster and simpler than the joint variant (REQ §4.4 explicitly endorses local per-city).
- AQ-gated rejection is hard: a center with no aqueduct candidate is **silently dropped**, even if its `InfluenceField` is the highest on the board (REQ §4.3).

### 6.7 Acceptance tests

1. On a board with no rivers / lakes / mountains anywhere, `fallback_solve(N=1)` raises `FallbackInfeasible`.
2. On a board with one valid AQ tile, `fallback_solve(N=1)` returns a `Placement` with one city, AQ-Hansa adjacent, and a non-zero score.
3. For N=2 on a board where templates do not fit, the two cities returned obey `distance(C0, C1) >= MIN_CITY_SPACING`.

### 6.8 Notes / gotchas

- The greedy here is *local* — it is **expected** to underperform `fit.py` when any template is applicable. The point of this module is to never crash the solver, not to be smart.
- Do not import `fit.fit_template` — fallback never calls into the template fitter.

---

## 7. Module: `algorithm/solve.py`

**Owner role:** `solve-worker`

### 7.1 File path

`/algorithm/solve.py`

### 7.2 Allowed imports

- `typing`
- `algorithm.fit` — `fit_best`, `Placement`, `StartingCity`
- `algorithm.fallback` — `fallback_solve`
- `algorithm.templates` — `load_default_library`
- *(no direct `hex` / `score` imports — those flow through `fit` / `fallback`)*

### 7.3 Public exports

```python
solve(board, starting_city, n, *, library=None, progress_callback=None) -> Placement
```

### 7.4 Behavior

```
def solve(board, starting_city, n, *, library=None, progress_callback=None):
    sc = StartingCity.from_dict(starting_city, board)
    if n == 0:
        return Placement(cities=(), score=0, template_name=None, ...)

    lib = library or load_default_library()
    progress_callback and progress_callback(0, 2, "fitting templates")

    placement = fit_best(board, lib, sc, n)
    progress_callback and progress_callback(1, 2, "templates done")

    if placement is None:
        placement = fallback_solve(board, sc, n)
    progress_callback and progress_callback(2, 2, "done")
    return placement
```

### 7.5 Behavior contract

- `solve` is the **only** module-level entry point for external callers (`main.py`, `visualizer.py`, future tests). All other modules are implementation detail.
- `solve` does not raise on "no solution" — `fallback_solve` itself raises `FallbackInfeasible`. `solve` re-raises.
- `progress_callback` (if given) is called at least at start, mid, and end. Callers tolerate any total / completed pair (see `main.py::TerminalProgressBar`).

### 7.6 Acceptance tests

1. `solve(board, sc, 0)` returns an empty `Placement` with `score == 0`.
2. `solve(test_board.build_three_river_plains_board()[0], starting_city, 3)` returns a `Placement` with `template_name == "triangle_3"` and `score >= TRIANGLE_3_TARGET` (resources/rivers may push it above).
3. `solve(...)` on a board with no fittable templates returns a fallback `Placement` (`template_name is None`).

### 7.7 Notes / gotchas

- `n` should be validated as `>= 0`; negative values raise `ValueError`.
- The `score`/`weighted_total()` API on `Placement` is consumed by `main.py` and `visualizer.py`. See §9 for the compatibility shim.

---

## 8. Module: `algorithm/__init__.py`

**Owner role:** `integration-worker`

### 8.1 File path

`/algorithm/__init__.py`

### 8.2 Allowed imports

- `algorithm.solve`, `algorithm.fit`, `algorithm.score`, `algorithm.templates`, `algorithm.hex`

### 8.3 Public exports (used by `main.py` / `visualizer.py`)

```python
# District kind constants
H, CH, HB, AQ, OTHER

# Scoring mode constants (legacy: REQUIREMENTS_REDO.md drops combination, but
# main.py still imports these — keep the constants, treat COMBINATION as a
# no-op alias for HANSA_ONLY in the redo).
HANSA_ONLY    = "hansa_only"
COMBINATION   = "combination"

# Types
Coord                 # from hex
Placement             # from fit
CityPlacement         # from fit
StartingCity          # from fit
Solution              # alias for Placement (compat with visualizer.py)

# Entry point
solve                 # from solve

# hex submodule (visualizer.py imports `algorithm.hex.distance` directly)
from . import hex     # exposes algorithm.hex.distance, .Coord
```

### 8.4 The `Solution` shim

`visualizer.py` imports `Solution` and expects it to have:
- `solution.cities: list[result-with-.assignment-and-.score]`
- `solution.score.production`, `solution.score.gold`
- `solution.weighted_total()`
- `solution.mode`

The redo's `Placement` doesn't natively carry `gold` or `mode`. Provide a thin compatibility wrapper:

```python
@dataclass
class _ScorePair:
    production: int
    gold: int = 0

@dataclass
class _CityResult:
    city: object        # has .coords
    assignment: object  # has .hansa/.commhub/.harbor/.aqueduct
    score: _ScorePair

class Solution:
    """Adapter that lets the existing main.py/visualizer.py consume a
    Placement without changes."""
    def __init__(self, placement: Placement, mode: str = HANSA_ONLY):
        self._p = placement
        self.mode = mode
        self.score = _ScorePair(production=placement.score, gold=0)
        self.cities = [self._adapt(c) for c in placement.cities]

    def weighted_total(self) -> float:
        return float(self.score.production)

    def _adapt(self, cp: CityPlacement) -> _CityResult: ...
```

`solve(...)` returns a raw `Placement`; `__init__` provides a `solve_compat(...)` that wraps it as `Solution` for legacy callers. `main.py` is updated (small change) to call `solve_compat`.

### 8.5 Acceptance tests

1. `from algorithm import solve, Placement, HANSA_ONLY, H, CH, HB, AQ` — all imports succeed.
2. `from algorithm.hex import distance, Coord` — succeeds (visualizer.py imports this path).
3. The legacy `main.py` runs end-to-end against the new package without source changes beyond a single-line import switch (`solve` ⇒ `solve_compat`).

---

## 9. Cross-cutting Concerns

### 9.1 Resource handling

- `score.py` is the *only* place that reads resources off the board (via `build_resource_index`).
- Templates do **not** depend on resources for their structural validity. Resources only modulate the final score.
- This means `fit_template` may pick a sub-optimal anchor when resources strongly favour a different one — that's accepted; resources are bonuses on top of the geometric optimum.

### 9.2 Starting-city districts as "free" Hansa neighbours

The starting city's CH, Harbor, and Aqueduct already exist (or may already exist — they're optional in the input). They appear in `build_district_index` and contribute to Hansa scoring exactly like new-city districts.

### 9.3 Coordinate origin & rotation invariants

Every template offset is expressed **relative to its anchor**. Rotations are applied *before* adding the anchor. Mirror is applied *before* rotation. This composition order is fixed across the project — `hex.rotate_offsets(offsets, k, mirror=True)` is the canonical entry point.

### 9.4 What is NOT modular here

These are integrator concerns, not module-worker concerns:
- Concrete offset tables for `TRIANGLE_3` and `DOUBLE_2` (TBD; user to derive from a saved board — see `REQUIREMENTS_REDO.md` §7).
- The visualizer / `Solution` adapter shape (lives in `__init__.py`, but driven by external file `visualizer.py`).
- `main.py` updates (one-line import change).

---

## 10. Assumptions Awaiting User Confirmation

These are the empirical / design numbers I committed to in this spec. The module workers will encode them as constants in `algorithm/__init__.py` (or `templates.py` for template-specific). One agree/disagree per row:

| # | Assumption | Default value used |
|---|---|---|
| A1 | Triangle-3 baseline (no resources) max combined Hansa production | **33** |
| A2 | Per-Hansa max inside the canonical triangle-3 layout | **11** |
| A3 | Double-2 baseline max combined Hansa production | **15** (8 + 7 split) |
| A4 | Composite (3+2) baseline = A1 + A3 | **48** |
| A5 | Min city spacing | **4** |
| A6 | Working radius for districts | **3** |
| A7 | Cluster radius (beyond which two cities cannot interact) | **6** |
| A8 | Number of orientations per anchor sweep (rotations × mirrors) | **12** |
| A9 | Tie-break order on equal-scoring placements | (a) more aqueducts adjacent to Hansas, (b) lower per-city score variance |
| A10 | Harbor in templates is per-center optional, not a separate template variant | **per-center optional** |
| A11 | `COMBINATION` mode in the redo is a no-op alias for `HANSA_ONLY` | **alias** |

Reply only with disagreements (e.g. "A2 should be 10"). Silence = all eleven accepted.

---

## 11. Implementation Order Recap

For maximally parallel AI distribution:

| Wave | Workers | Modules |
|---|---|---|
| 1 (parallel) | hex-worker, score-worker | `hex.py`, `score.py` |
| 2 | template-worker | `templates.py` (uses hex; offsets stubbed if unknown) |
| 3 (parallel) | fit-worker, fallback-worker | `fit.py`, `fallback.py` |
| 4 | solve-worker | `solve.py` |
| 5 | integration-worker | `__init__.py` + `Solution` shim + `main.py` one-line patch |

Each worker's contract is fully self-contained in its section above. The integrator (you, or me on a follow-up turn) wires it together and runs the §6 / §7 acceptance tests against the synthetic board in `test_board.py`.
