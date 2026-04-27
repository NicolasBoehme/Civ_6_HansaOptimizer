# Civ 6 Hansa Placement Optimizer — Project Brief

---

## 1. Project Overview

A placement optimizer for the German civilization's Hansa district in Civilization 6. Given a fixed starting city and a request to place N additional cities, the algorithm determines the optimal positions for:
- New city centers
- Hansa districts
- Commercial Hubs
- Harbors (coastal cities only)
- Aqueducts

**Scope boundary:** The hex grid, map rendering, and UI are implemented by a separate collaborator. This project delivers the optimization algorithm only. The map is read in as double-width (doubled) hex coordinates with terrain, resource, river, and existing district data already encoded.

---

## 2. What We Are Optimizing

### Scoring Modes (user-selectable)
- **Hansa Production Only** — maximize total production across all Hansas
- **Combination Mode** — maximize a weighted sum of Hansa production + Commercial Hub gold + Harbor gold, where the exchange rate (1 production = X gold) is a user-set parameter

Total yields (food, production from worked tiles) are noted as relevant for a later phase but are **not part of the core optimization objective now**.

### The Benefit Matrix (complete scoring oracle)

Every adjacency bonus reduces to a lookup in this table. Pair notation (a / b) = row district gets +a production/gold, column district gets +b.

| | Hansa | Comm Hub | Harbor | Aqueduct | Other District |
|---|---|---|---|---|---|
| **Hansa** | +1 / +1 | +2 / +1 | +2 / +1 | +2 / +0 | +1 / +1 |
| **Comm Hub** | — | — | +1 / +1 | — | +1 / +1 |
| **Harbor** | — | — | — | — | +1 / +1 |

Note: Aqueduct is asymmetric — it gives the Hansa +2 production but does not receive a production bonus back. Other districts (Campus, Theater Square, etc.) are treated as generic "+1 adjacency" sources for the Hansa but are not themselves optimized.

### Full Hansa Adjacency Bonus Breakdown
- **+2 Production** per adjacent Commercial Hub (any city)
- **+2 Production** per adjacent Harbor (any city)
- **+2 Production** per adjacent Aqueduct
- **+1 Production** per adjacent other district (any city, including other Hansas)
- **+2 Production** per adjacent luxury or strategic resource tile
- **+1 Production** per adjacent bonus resource tile

### Commercial Hub Adjacency Bonus Breakdown
- **+2 Gold** per adjacent river (baked into map tile data — treat as a fixed per-tile property)
- **+1 Gold** per adjacent district (any city)

### Harbor Adjacency Bonus Breakdown
- Base gold from trade routes and coastal resources (fixed per tile — read from map)
- **+1 Gold** per adjacent district (any city)

---

## 3. Game Rule Constraints

### City Center Placement
- Cannot be placed on: water, mountain, natural wonder tiles
- Minimum distance between any two city centers: **4 hex tiles** (so at least 2 tiles exist between borders — standard Civ 6 rules; confirm with implementer if custom rules apply)
- The starting city's position is fixed and provided as input

### District Placement (General)
- Must be within the city's **working radius: distance ≤ 3** from city center (in hex distance)
- Cannot be placed on: water, mountain, natural wonder tiles
- Cannot be placed on the city center tile itself
- At most **one district per tile** globally (districts from different cities cannot share a tile)
- Each city has exactly **one Hansa** and **one Commercial Hub**

### Harbor
- Can only be placed on **coastal tiles** — tiles that are themselves adjacent to a water tile
- Only cities with at least one coastal tile in their working radius can build a Harbor
- Each city has at most **one Harbor**

### Aqueduct
- Must be placed on a tile that is **adjacent to the city center** (within 1 hex)
- That tile must also be **adjacent to a river, lake, or mountain tile**
- Each city has at most **one Aqueduct**
- In practice this yields 0–3 candidate tiles per city — enumerate exhaustively

### Cross-City District Interaction
This is the defining mechanic of the German Hansa. Districts from **different cities** can be adjacent on the map and provide mutual bonuses. A Hansa in City A gets +2 production from a Commercial Hub in City B if their tiles are adjacent. This interaction is what makes placement optimization non-trivial.

---

## 4. Input Format

- Map grid encoded in **double-width (doubled) coordinates**
- Each tile contains: terrain type, resource type (if any), river flag, existing district type (if any), coastal flag
- The starting city is provided as: city center tile, Hansa tile, Commercial Hub tile, Harbor tile (if applicable), Aqueduct tile (if applicable)
- N = number of new cities to optimize for (user input)
- Scoring mode = "hansa_only" or "combination" (user input)
- If combination mode: exchange rate weight W (user input, default suggestion: 1.0)

### Double-Width Coordinate Adjacency
In double-width coordinates, the 6 neighbors of tile (col, row) are:
```
(col-2, row),  (col+2, row)           ← left, right
(col-1, row-1), (col+1, row-1)        ← upper-left, upper-right
(col-1, row+1), (col+1, row+1)        ← lower-left, lower-right
```
Hex distance formula (convert to cube coords for correctness — implementer's responsibility).

---

## 5. Algorithm Design

### Mathematical Characterization
The problem is a **Quadratic Integer Program (QIP)** — a variant of the Maximum Weight Subgraph problem. Formally:

```
Maximize:  Σ_{adjacent pairs (t₁,t₂)} B[d₁,d₂] · x_{c₁,d₁,t₁} · x_{c₂,d₂,t₂}

Subject to:
  x_{c,d,t} ∈ {0,1}
  Σ_t x_{c,d,t} = 1              (each district placed exactly once per city)
  Σ_{c,d} x_{c,d,t} ≤ 1         (at most one district per tile globally)
  Placement validity constraints  (terrain, radius, coastal, city center adjacency)
```

The quadratic objective is linearizable for small clusters; the locality of hex adjacency makes the problem tractable despite its NP-hard general form.

### Phase 1 — Pre-computation: Influence Field
For every tile t on the map, compute:

```
InfluenceField(t) = Σ_{t' adjacent to t} fixed_district_bonus(t')
```

Where fixed districts = starting city's Hansa, CommHub, Harbor, Aqueduct + all resource tiles (luxury/strategic give +2, bonus give +1 to adjacent Hansas).

This is an O(tiles) computation. It produces a scalar "free bonus" map — how much a Hansa placed at t gains from already-fixed elements, before any new city districts are considered. This map is the foundation for all subsequent pruning.

### Phase 2 — Candidate City Center Generation
Filter all map tiles to valid city center positions:
- Remove water, mountain, natural wonder tiles
- Remove tiles within distance 3 of any existing city center (minimum spacing rule)
- Flag each candidate as **coastal** (has ≥1 coastal tile in radius 3) or **inland**
- Flag candidates within distance 6 of any fixed district as **high-synergy candidates** — cross-city district adjacency is geometrically possible here

### Phase 3 — Cluster Formation
Build an interaction graph over candidate city centers:
- Two candidates are **connected** if their centers are within **6 hex tiles** of each other (the threshold at which districts from both cities could be adjacent — each district is within 3 tiles of its city center, so 3+3=6)
- Connected components of this graph = **independent clusters**
- Clusters are solved separately — this is the primary search space reduction

Cities outside all clusters (isolated candidates) are optimized purely on local criteria: InfluenceField + within-city district geometry.

### Phase 4 — Aqueduct Pre-enumeration
For each candidate city center, enumerate Aqueduct candidate tiles:
```
Aqueduct candidates = {t : dist(t, city_center) = 1} ∩ {t : t is adjacent to river, lake, or mountain}
```
Typically 0–3 tiles. Enumerate all possibilities — negligible cost.

### Phase 5 — Dead Tile Elimination (Dominance Pruning)
For each candidate Hansa tile within a city's working radius:

**Dead tile rule:** Eliminate tile t as a Hansa candidate if:
- All 6 neighbors of t are: water, mountain, city center, or natural wonder
- AND InfluenceField(t) = 0 (no fixed bonuses)
- Result: Hansa there scores 0 and is dominated by any tile with positive influence or neighbor potential

**Local dominance rule:** Tile A dominates tile B as a Hansa candidate if:
- InfluenceField(A) ≥ InfluenceField(B)
- The set of A's neighbors that are reachable by valid new districts is a superset of B's reachable neighbors
- Result: B is eliminated from consideration

### Phase 6 — Within-City Upper Bounds
For each candidate city, compute the **theoretical maximum Hansa score** (useful for branch-and-bound bounding):

```
MaxWithinCity(city) =
    InfluenceField(best_hansa_tile)
    + 2 × (1 if CommHub can be adjacent to Hansa)
    + 2 × (1 if Harbor can be adjacent to Hansa, coastal only)
    + 2 × (1 if Aqueduct can be adjacent to Hansa)
    + cross_city_max (bounded by max bonus from other cities in cluster)
```

Reference thresholds (ignoring resources and cross-city):
- Inland, no Aqueduct possible: **+2 max** (CommHub only)
- Inland with Aqueduct: **+4 max** (CommHub + Aqueduct adjacent to Hansa)
- Coastal, no Aqueduct: **+4 max** (CommHub + Harbor)
- Coastal with Aqueduct: **+6 max** (CommHub + Harbor + Aqueduct — requires Hansa in triangle with all three)

The "district triangle" — three mutually adjacent hexes each holding one district — is the canonical optimal within-city configuration. The optimizer should attempt to find this triangle before evaluating cross-city placements.

### Phase 7 — Branch and Bound (Per Cluster)
For each cluster of interacting candidate cities, run branch and bound:

1. **Greedy initialization:** Place all districts using a greedy highest-InfluenceField-first heuristic. This gives a valid complete solution as the initial lower bound.

2. **Branching:** Order placement decisions by decreasing upper bound impact (Hansa placements first, since they have the most adjacency interactions).

3. **Bounding:** At each partial assignment:
   ```
   UpperBound = score_so_far
              + Σ_{unplaced Hansas} max_possible_bonus(Hansa_i)
              + Σ_{unplaced CommHubs/Harbors} max_district_contribution
   ```
   If UpperBound ≤ best_complete_solution, prune this subtree.

4. **Termination:** When all branches are either completed or pruned.

### Phase 8 — Output
For each optimal configuration found:
- City center coordinates for each new city
- Hansa, CommHub, Harbor, Aqueduct coordinates per city
- Score breakdown: per-district, per-city, and total
- In combination mode: production and gold reported separately alongside the weighted total
- Flag which adjacency bonuses are being utilized (useful for the user to understand the placement logic)

---

## 6. Key Algorithmic Insights Summary

1. **Locality:** A Hansa interacts only with its 6 immediate neighbors. This bounds the interaction radius and enables cluster decomposition.

2. **Cluster decomposition:** Cities whose centers are >6 tiles apart cannot interact. Solve independently. This is the single largest search space reduction.

3. **Influence field pre-computation:** Converts fixed-district bonuses into a per-tile scalar map in O(tiles), enabling fast candidate ranking and dead tile elimination.

4. **Aqueduct heavy restriction:** Only 0–3 candidate tiles per city due to dual adjacency constraint (city center + water/mountain feature). Always enumerate exhaustively.

5. **District triangle:** Three mutually adjacent districts (Hansa + CommHub + Harbor/Aqueduct) is the canonical optimal within-city configuration and should be used as both a baseline and a pruning reference.

6. **Asymmetric benefit matrix:** Aqueduct is asymmetric (gives +2 to Hansa, receives nothing). This means CommHub/Harbor adjacency is preferred over Aqueduct adjacency for the CommHub and Harbor's own scoring, but all three are equally valuable for the Hansa.

7. **Cross-city Hansa-Hansa adjacency:** Two Hansas from different cities adjacent to each other give +1/+1 production. Less valuable than CommHub (+2/+1) but still worth capturing in dense city clusters.

---

## 7. Open Questions / Decisions Pending

| Question | Status | Notes |
|---|---|---|
| Are other districts (Campus, Theater Square etc.) placed by the algorithm or treated as fixed external bonuses? | **Pending** | Currently modeled as fixed "+1 generic district" contributors only |
| Exact minimum city spacing (4 tiles or 3 tiles)? | **Pending** | Standard Civ 6 is 4; confirm with implementer |
| Harbor base gold — is this encoded in map tile data or computed separately? | **Pending** | Assumed to be in map tile data |
| Combination mode default exchange rate (1 prod = X gold)? | **Pending** | Suggest 1.0 as default, user-configurable |
| Joint optimization of N cities simultaneously vs. sequential? | **Pending** | Joint gives better results especially when new cities interact with each other; sequential is faster. Recommend joint for N≤3, sequential fallback for larger N |
| Pareto front output vs. single weighted score in combination mode? | **Decided: weighted score** | Simpler and sufficient; weight is user-configurable |

---

## 8. Files / Components the Algorithm Needs From the Implementer

- `map[col][row]` → struct with: terrain, resource_type, resource_tier (bonus/luxury/strategic), has_river (bool), is_coastal (bool), existing_district (type or null), city_id (if claimed)
- `starting_city` → struct with: center_coords, hansa_coords, commhub_coords, harbor_coords (nullable), aqueduct_coords (nullable)
- `hex_distance(a, b)` → integer distance function for double-width coordinates
- `neighbors(t)` → list of 6 adjacent tiles for double-width coordinates
- `tiles_within_radius(center, r)` → all tiles within hex distance r

---

## 9. Out of Scope (For Now)

- City tile yields (food, production from worked tiles)
- Culture borders and tile ownership
- Civics/technology unlock requirements for districts
- Multi-player or AI city considerations
- Turn-by-turn build order optimization
- Districts other than Hansa, Commercial Hub, Harbor, Aqueduct

---

*Brief compiled from design discussion. Last updated: 2026-04-24*
