# Hansa Optimizer — Algorithm Redo Requirements

Last updated: 2026-04-30
Status: Draft — pre-implementation

---

## 1. Motivation

The current `algorithm/` package (bnb / candidates / cluster / scoring / solve) is being **deleted** and replaced. The existing approach is a general QIP / branch-and-bound solver that treats every tile as an open variable. In practice, optimal multi-city Hansa layouts in Civ 6 collapse to a **small set of geometric templates**: triangles of city centers with districts packed at the shared interior. The redo replaces general search with **template matching against pre-computed optimal configurations**, falling back to local search only when no template fits.

---

## 2. New Objective (narrowed)

- **Single objective: maximise total Hansa production.**
- Combination mode (gold weighting) is **out of scope** for the redo. Commercial Hub and Harbor are placed only insofar as they feed Hansa adjacency; their own gold yield is not scored.
- Aqueduct is placed only when it can be made adjacent to that city's Hansa (+2 prod) — otherwise the city skips it.

The Benefit Matrix from the project brief still applies, but the optimizer only sums the **Hansa-row** contributions.

---

## 3. Geometric Model the Algorithm Targets

The user's empirical insight, which the algorithm should encode directly:

- **N = 2 cities:** the optimal layout is a known fixed pattern. Target ≈ **8 + 7 = 15** combined Hansa production with a "double" arrangement.
- **N = 3 cities:** place the three city centers in a **triangle**, with the **Aqueduct of each city pointing toward the triangle's centroid**. This concentrates each city's Hansa near the shared interior so each Hansa is adjacent to as many other-city districts (Comm Hubs, Harbors, Aqueducts, other Hansas) as possible. Target **≥ 30 combined Hansa production**.
- **N = 5 cities:** "5-1 triangle, 1 double" — one tight 3-city triangle plus a 2-city double arrangement, treated as two independent sub-problems.
- **General rule for placement:**
  1. Hansas should **not be adjacent to other Hansas** when a hub-adjacency is available instead (Hansa↔Hansa = +1/+1, Hansa↔Hub = +2/+1).
  2. Each Hansa should be adjacent to as many **hubs** (Comm Hub / Harbor / Aqueduct) from any city as geometry permits.
  3. A city is only worth placing where a valid **Aqueduct tile exists** (city-center-adjacent tile that also touches river/lake/mountain) AND that Aqueduct tile can be made adjacent to that city's Hansa. Otherwise the city is downgraded or rejected.

---

## 4. Required Behaviour

### 4.1 Template library
The algorithm ships with a hard-coded library of **canonical optimal configurations** indexed by N (number of new cities) and shape:
- `triangle_3` — 3 centers forming an equilateral-ish hex triangle, with the canonical interior district packing (3 Hansas + 3 Comm Hubs + 3 Aqueducts pointing inward, optionally Harbors if coastal).
- `double_2` — 2 centers at the spacing that maximises shared-border districts (the 8 + 7 case).
- `triangle_3 + double_2` — for N = 5.
- (Extensible: more templates may be added later — the loader must be data-driven.)

Each template specifies, in **relative double-width offsets from an anchor tile**:
- City center offsets
- Per-city district offsets (Hansa, Comm Hub, Aqueduct, optional Harbor)
- Required tile properties at each offset (e.g. "this tile must be river-adjacent", "this tile must not be water/mountain")
- Pre-computed Hansa production score, assuming neutral terrain and no resources

### 4.2 Template fitting
Given a map and a fixed starting city, the solver:
1. Enumerates all valid **anchor positions and rotations** (6 hex rotations, optional mirror) of each applicable template.
2. For each placement, validates all template tile-property constraints against the actual map.
3. Validates the city-spacing rule against the starting city and other placed centers.
4. **Scores** the placement by computing real Hansa production on the actual map — including resource bonuses, river/coast bonuses on hubs (insofar as they affect Hansa adjacency, which they don't directly — but resources adjacent to Hansa do), and any cross-template synergy with the starting city.
5. Returns the best-scoring valid template placement.

### 4.3 Aqueduct-gated city placement
A candidate city center is **rejected** if no aqueduct tile exists that is simultaneously:
- Adjacent to the center, AND
- Adjacent to a river / lake / mountain, AND
- Position-compatible with making the Hansa adjacent to it.

This rule applies both inside template fitting (a template instance is invalid if any of its centers fails this) and in the fallback path.

### 4.4 Fallback (no template fits)
If no template can be placed validly for the requested N:
- Solve each city **independently and locally** by:
  1. Pick the city center that maximises the InfluenceField + has a valid aqueduct.
  2. Place Hansa on the in-radius tile maximising local adjacency (resources + the city's own future Comm Hub + Aqueduct if buildable, forming the "district triangle").
  3. Place Comm Hub and Aqueduct adjacent to that Hansa.
- Report clearly that fallback was used and templates did not fit.

### 4.5 Output (unchanged from project brief §8 / Phase 8)
Per new city: center, Hansa, Comm Hub, Aqueduct, optional Harbor coordinates, plus per-Hansa score breakdown and total. Additionally: **which template (if any) was matched, at which anchor and rotation.**

---

## 5. Code Changes

### 5.1 Delete
The entire current `algorithm/` package contents — `bnb.py`, `candidates.py`, `cluster.py`, `features.py`, `hex.py`, `model.py`, `scoring.py`, `solve.py`. Keep `__init__.py`.

`main.py`, `visualizer.py`, `test_board.py`, and the `Tile Logic/` package stay untouched (board, tile, river, rendering are still owned by the collaborator).

### 5.2 Add
New modules under `algorithm/`:
- `hex.py` — minimal: double-width neighbours, hex distance, rotation of an offset list around the origin. (Re-introduced; smaller than the deleted version.)
- `templates.py` — the template data structures and the canonical template library (`triangle_3`, `double_2`, composite for N=5). Templates expressed as relative offsets + tile-property predicates.
- `fit.py` — anchor enumeration, rotation/mirror, validity check, scoring of a placed template.
- `fallback.py` — the local per-city greedy described in 4.4.
- `solve.py` (rewritten) — top-level entry: takes the board + starting city + N, returns the placement. Tries templates first, fallback second.
- `score.py` — Hansa-only production scorer used by both paths. (Replaces `scoring.py`.)

### 5.3 Public API
`solve(board, starting_city, n_new_cities) -> Placement` is the only entry point. `main.py` is updated to call it; `visualizer.py` consumes the same `Placement` shape it does today.

---

## 6. Acceptance Criteria

1. On a flat test map with rivers arranged for a clean 3-city triangle, the optimizer returns a `triangle_3` template match with **combined Hansa production ≥ 30**.
2. On a 2-city test map matching the canonical "double" configuration, the optimizer returns `double_2` with combined Hansa production **≥ 15** (i.e. the 8 + 7 case).
3. For N = 5 on a map that admits both, the optimizer returns the composite (`triangle_3 + double_2`) and the score equals the sum of the two sub-scores.
4. A candidate city center with no valid aqueduct tile is **never** chosen when an alternative center with a valid aqueduct exists at comparable score.
5. The fallback path is exercised by a test where no template fits, and produces a valid (if suboptimal) placement.
6. No code from the deleted `bnb.py` / `cluster.py` / `candidates.py` remains.

---

## 7. Open Questions

| Question | Notes |
|---|---|
| Exact tile coordinates of the canonical `triangle_3` template | User to provide (or to be derived from a saved board); needed before implementation can be completed. |
| Exact tile coordinates of `double_2` (the 8 + 7 case) | Same — needs concrete offsets. |
| Should Harbor be part of templates only when all centers are coastal, or as an optional "upgrade" branch per template? | Lean: optional per-center upgrade if that center is coastal. Confirm. |
| Mirror as well as rotate when fitting? | Default yes (12 orientations total). Cheap. Confirm. |
| Behaviour when multiple templates score equally | Tie-break on (a) more aqueducts adjacent to Hansas, (b) lower variance across cities. Confirm. |

---

## 8. Out of Scope for the Redo

- Combination (gold) scoring mode.
- Worked-tile yields, food, growth.
- Districts beyond Hansa / Comm Hub / Harbor / Aqueduct.
- Automated discovery of new templates — the library is curated by hand for now.
