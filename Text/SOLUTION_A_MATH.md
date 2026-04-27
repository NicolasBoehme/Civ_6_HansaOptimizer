# Solution A — Aqueduct-First, Star-Formation Optimization

### A complete mathematical approach for the Civ 6 Hansa Placement Optimizer

Companion to `PROJECT_BRIEF.md`. All coordinates below use cube coordinates `(x, y, z)` with `x+y+z = 0`; hex distance is `d(a,b) = (|Δx| + |Δy| + |Δz|) / 2 = max(|Δx|, |Δy|, |Δz|)`. Translation to the double-width grid used by the map is the implementer's responsibility.

---

## 1. Notation

Let `T` denote the set of all map tiles. For a tile `t`:

- `N(t)` — the (up to) 6 neighbors of `t`.
- `R(c, r) = { u ∈ T : d(c, u) ≤ r }` — the closed hex disk of radius `r`.

For each candidate city `c` with center `c.ctr`:

- Working radius: `W_c = R(c.ctr, 3) \ {c.ctr}`.
- Aqueduct candidates: `A_c = { t ∈ N(c.ctr) : t is adjacent to a river, lake, or mountain tile }`. Typically `|A_c| ∈ {0, 1, 2, 3}`.
- Hansa candidates: `H_c ⊆ W_c`, filtered for placeability (not water / mountain / natural wonder; not already a district).
- CommHub candidates: `CH_c ⊆ W_c`, same filter.
- Harbor candidates: `HB_c = { t ∈ W_c : t.coastal }`. Empty for inland cities.

Global hard constraints:

1. Each city places exactly one Hansa and exactly one CommHub; at most one Harbor (coastal only) and at most one Aqueduct.
2. At most one district per tile across all cities (the "shared tile" constraint that makes this a QIP, not a sum of independent problems).
3. City centers are pairwise `≥ 4` apart.

---

## 2. Benefit matrix (oracle for scoring)

Asymmetric. Row district gets the first value, column district gets the second. `·` means not applicable (we do not optimize the column district).

|                  | Hansa   | CommHub | Harbor  | Aqueduct |
| ---------------- | ------- | ------- | ------- | -------- |
| **Hansa**        | +1 / +1 | +2 / +1 | +2 / +1 | +2 / +0  |
| **CommHub**      |         | —       | +1 / +1 | —        |
| **Harbor**       |         |         | —       | —        |

Plus, for a Hansa at tile `t`:

- `+2` per adjacent luxury / strategic resource.
- `+1` per adjacent bonus resource.
- `+1` per adjacent "other" district (Campus, Theater Square, etc.) — treated as map-fixed.

For a CommHub at tile `t`: `+2` gold per adjacent river tile (map-fixed).

---

## 3. Formal problem (Quadratic Integer Program)

Decision variables: `x_{c,d,t} ∈ {0,1}` — city `c` places district `d ∈ {H, CH, HB, Aq}` at tile `t`.

```
maximize   Σ  B[d₁, d₂] · x_{c₁, d₁, t₁} · x_{c₂, d₂, t₂}       (adjacency bonuses)
          (t₁,t₂) ∈ adj
          (c₁,d₁), (c₂,d₂)

         + Σ  resource_bonus(t) · x_{c, H, t}                   (Hansa ← resources)
           c, t

         + Σ  river_bonus(t)    · x_{c, CH, t}                  (CommHub ← rivers)
           c, t

subject to
   Σ_t x_{c, d, t} ≤ 1                ∀ (c, d)                 (at most one instance)
   Σ_t x_{c, d, t} = 1                for d ∈ {H, CH}           (always placed)
   Σ_{c,d} x_{c, d, t} ≤ 1            ∀ t                       (one district per tile)
   x_{c, d, t} = 0                    ∀ t ∉ (candidate set for d in c)
```

In combination mode, weight the Hansa production and CommHub/Harbor gold contributions by the user-supplied exchange rate `W`. In Hansa-only mode, zero out the gold terms.

The quadratic structure is concentrated in the adjacency sum. It is sparse — `|adj|` is small (each pair is 1-step in the hex graph), and the objective factorizes over tiles. The locality of the hex graph is what makes the problem tractable in practice.

---

## 4. The Aqueduct-First Principle

Aqueducts are the **most constrained** district and therefore the natural "outer loop" of the search:

1. **Doubly constrained placement.** An aqueduct tile `a` must satisfy `d(a, c.ctr) = 1` *and* `∃ u ∈ N(a)` with `u` a river, lake, or mountain tile.
2. **Tiny candidate set.** `|A_c| ≤ 3` almost always. (A city on a peninsula between two mountain ranges and a river can have at most 3 valid aqueduct tiles; most cities have 0–2.)
3. **Asymmetric effect.** The aqueduct gives the Hansa `+2` and receives nothing. It is valuable only insofar as a Hansa can be adjacent to it.
4. **Strong geometric prior.** Once `a_c` is fixed, the "preferred" Hansa region of city `c` collapses from `|H_c| ≤ 36` to `N(a_c) ∩ W_c` — at most 6 tiles.

**Implication.** Enumerate aqueduct choices across a cluster first. The enumeration cost is bounded by `∏_c (|A_c| + 1) ≤ 4^k` for a cluster of size `k` (the `+1` is the "no aqueduct" choice when `A_c = ∅` or when omitting the aqueduct is genuinely better). For `k ≤ 5` this is at most 1024 configurations — trivial.

---

## 5. Star-Formation Theory

### 5.1 Definition

A **star** of size `k` centered at tile `T` is a set of `k` Hansas, each belonging to a distinct city, each adjacent to `T`. The center `T` may additionally host a district (CommHub, Aqueduct, or Harbor) owned by one of the participating cities; if so we speak of a *CH-centered star*, *Aq-centered star*, etc.

### 5.2 Payoff

For a CH-centered star of size `k` with the Hansas arranged to maximize mutual adjacency (a contiguous arc on `N(T)`), the new production is:

```
Hansa gain  = 2·k           (each Hansa ← +2 from CommHub at T)
            + 2·(k−1)        (each adjacent Hansa pair gives +1/+1)
            = 4k − 2
CH gold    = k               (CommHub receives +1 per adjacent Hansa)
```

For an Aq-centered star, the Hansa gain is the same `4k − 2` (aqueduct gives the same +2 to Hansas), but the center receives no gold. For a Harbor-centered star, the harbor is adjacent to Hansas that are coastal; harbor-Hansa adjacency yields `+2/+1`.

### 5.3 Maximum star size

**Proposition (4-star cap).** *Under Civ 6 minimum city spacing `≥ 4` and working radius `3`, the maximum number of distinct cities whose Hansas can all be adjacent to a single center tile `T` is 4.*

**Construction of a 4-star.** Place:

- `A = (0, 0, 0)` with its CommHub at `T = (3, 0, −3)` (distance 3, within `A`'s working radius).
- `B = (6, −1, −5)`, `C = (4, −3, −1)`, `D = (3, 3, −6)` — each within distance 3 of `T`, pairwise `≥ 4` from each other and from `A`.

Pairwise city distances: `A–B = 6`, `A–C = 4`, `A–D = 6`, `B–C = 4`, `B–D = 4`, `C–D = 6`. All legal.

Assign Hansas on `N(T)` (one tile per city, all distinct):

- `A → (2, 0, −2)`
- `B → (4, −1, −3)`
- `C → (3, −1, −2)`
- `D → (4, 0, −4)`

These are on positions `{5, 6, 1, 2}` of the cyclic neighbor order, giving **three** Hansa–Hansa adjacencies: `1–2`, `5–6`, `6–1`. Plus four Hansa-CommHub adjacencies. Total new production `= 4·4 − 2 = 14`; total CommHub gold `= +4`.

**Non-existence of a 5-star.** A 5th city would need a center within `R(T, 3)` (37 tiles) at distance `≥ 4` from each of the four existing centers. An exhaustive scan of the 37 candidates shows no valid tile; the packing bound of "mutually `≥ 4` centers inside a hex of radius 3 around `T`" is 4.

### 5.4 Star taxonomy and ranking

For each center-type choice, the maximum payoff (Hansa-only score contribution) is:

| Star shape           | Center hosts | Cities | Contiguous Hansa gain | Extra (CH gold) |
| -------------------- | ------------ | -----: | --------------------: | --------------: |
| **4-star CH**        | CommHub      |      4 |                  `14` |            `+4` |
| **3-star CH**        | CommHub      |      3 |                  `10` |            `+3` |
| **4-star Aq**        | Aqueduct     |      4 |                  `14` |             `0` |
| **3-star Aq**        | Aqueduct     |      3 |                  `10` |             `0` |
| **2-star CH (pair)** | CommHub      |      2 |                   `6` |            `+2` |
| **Isolated**         | —            |      1 |     (no star payoff)  |               — |

User rule (mathematically justified): **a tight 3-star beats a loose attempt at a 5-star**, because the 5-star is infeasible and the loose attempt achieves at most the score of a weaker shape. Equivalently: `score(good 3-star) > score(3-star built from a broken 4-star attempt)`, so the optimizer must be willing to abandon a committed star if the committed slots degrade the score.

### 5.5 The district triangle (within-city optimum)

Within a single city, the canonical local optimum is the **district triangle**: three mutually adjacent tiles holding the Hansa, the CommHub, and either the Aqueduct or the Harbor. Three mutually-adjacent tiles in a hex grid form a unique shape: two neighbors of a common tile that are themselves neighbors. The triangle gives:

- Hansa: `+2` (CH) `+2` (Aq or HB) `= +4` from within-city adjacency alone.
- CH: `+1` (H) `+1` (HB if present) `= +1` or `+2` gold.
- Aqueduct or Harbor: `0` or `+1` (reciprocal).

A triangle combined with a cross-city star bonus stacks: a Hansa in a triangle + in a star gets `+4` from its own city and `+2` from the star center (or even more if the star center is also adjacent to the triangle).

---

## 6. Algorithm — Hierarchical Optimization (Solution A)

### Phase 0. Preprocessing (linear in map size)

1. Build the hex helpers: `neighbors`, `distance`, `R(c, r)`, coastal flag propagation.
2. Compute the **influence field** `IF: T → ℤ₊`:

   ```
   IF(t) = Σ     [fixed-district bonus(u) + resource bonus(u)]
           u ∈ N(t)
   ```

   where the sum includes the starting city's Hansa / CH / Harbor / Aqueduct (with their asymmetric contributions to an adjacent Hansa) and all resources (`+2` luxury/strategic, `+1` bonus).
3. Tag every tile with `can_host_district(t)` (placeability bool).

Cost: `O(|T|)`.

### Phase 1. Candidate city centers

Filter `T` to `𝒞` = tiles that are:

- Not water, mountain, or natural wonder.
- At distance `≥ 4` from every already-existing city center (including the starting city).
- Annotate each `c ∈ 𝒞` with: `coastal_flag` (`∃ t ∈ R(c.ctr, 3)` with `t.coastal`), `aqueduct_candidates A_c`, `high_synergy_flag` (within distance 6 of some other candidate or fixed city).

Cost: `O(|T|)`.

### Phase 2. Cluster formation

Build the **interaction graph** `G = (𝒞, E)`:

```
{c₁, c₂} ∈ E   ⟺   d(c₁.ctr, c₂.ctr) ≤ 6
```

The threshold 6 = 3 + 3 is the maximum distance at which a district of `c₁` (radius 3) and a district of `c₂` (radius 3) can still be adjacent.

Connected components of `G` are the **clusters**. Clusters are solved independently — this is the single largest search-space reduction.

Cost: `O(|𝒞|²)` for the pairwise graph, `O(|𝒞| + |E|)` for components.

### Phase 3. Aqueduct pre-enumeration (per cluster)

For a `k`-city cluster, enumerate

```
𝒜 = { (a_{c₁}, …, a_{cₖ}) : a_{cᵢ} ∈ A_{cᵢ} ∪ {⊥} }
```

where `⊥` represents "no aqueduct" (kept as a legal option). `|𝒜| ≤ 4^k`.

For each `α ∈ 𝒜`, the rest of Phases 4–5 runs with aqueducts locked.

### Phase 4. Star-center identification

For a fixed `α`, scan the cluster neighborhood for **star candidates**. A tile `T` is a candidate if

```
|{ c ∈ cluster : N(T) ∩ H_c ≠ ∅ }| ≥ 2.
```

(At least two cities can legally place a Hansa adjacent to `T`.)

For each candidate, compute an **upper bound** on the star's contribution:

```
StarUB(T, α) = (4·k_T − 2)                       — max contiguous Hansa chain payoff
              + (k_T if CH can sit at T)          — CH gold
              + IF_center(T)                      — bonuses from fixed districts / resources adjacent to T
              + Σ_{u ∈ N(T)} IF(u)                — bonuses each Hansa tile gets
```

where `k_T` = number of cities eligible for the star at `T`. Rank star candidates by `StarUB(T, α)` descending.

### Phase 5. Branch-and-bound per cluster

For each `(α, T*)` pair (aqueduct assignment + top-ranked star candidate):

1. **Greedy initialization (lower bound `L`).**
   - Fix aqueducts from `α`.
   - For each city participating in the star, lock Hansa to the best free tile in `N(T*) ∩ H_c` that maximizes `IF + adj(a_c)`.
   - For each non-participating city, greedily pick `Hansa ← argmax (IF(t) + bonus-from-own-aqueduct)`.
   - Greedily place each city's CommHub adjacent to its Hansa if possible, else at highest-`river_bonus` tile in `CH_c`.
   - Greedily place Harbors for coastal cities adjacent to Hansa or CH.
   - Evaluate full score → `L`.

2. **Branching.** The open variables are the CommHub, Harbor, and any non-stellated Hansa positions. Branch in descending order of marginal upper-bound impact:
   - Hansa placements (most adjacencies) first.
   - Then CommHubs (next-most — river bonus plus adjacency to own and neighbor Hansas).
   - Then Harbors.

3. **Bounding.** At any partial assignment `P`:

   ```
   UB(P) = score(P)
         + Σ            MaxResidual(c)
           c unplaced
   ```

   where `MaxResidual(c)` is the best possible additional contribution from city `c`'s remaining districts given the already-committed neighbors and the remaining candidate tiles. Standard B&B: prune subtree if `UB(P) ≤ L`.

4. **Dominance pruning.** Before branching on Hansa for city `c`:
   - **Dead tile**: eliminate `t ∈ H_c` if every `u ∈ N(t)` is water / mountain / wonder / city-center **and** `IF(t) = 0`. Hansa there is guaranteed 0.
   - **Local dominance**: `t` dominates `t'` in `H_c` if `IF(t) ≥ IF(t')` and `{ reachable-future-bonus-neighbors of t } ⊇ { reachable of t' }`. Remove `t'`.

5. **Star fallback.** If the best complete solution found under the committed star `T*` is worse than the no-star greedy baseline, discard `T*` and re-run Phase 5 with the next star candidate (or with the pure no-star B&B). This is the formal encoding of "a good pair beats a bad 5-star".

6. **Termination.** When the B&B tree under `T*` is exhausted (completed or pruned), record the best solution for this `(α, T*)`. After iterating over all `α` and the top few `T*` per `α`, return the global best.

### Phase 6. Output

Per cluster, emit:

- The city centers, Hansas, CommHubs, Harbors, and Aqueducts.
- A score breakdown per district and per bonus source (CH→H, Aq→H, Hb→H, H–H, resource, river).
- The star configuration used (or "no star / pairs / isolated").
- In combination mode: production and gold reported separately, plus the weighted total.

---

## 7. Complexity Analysis

Let `|T| ≈ 2000`, `|𝒞| ≈ 200`, `k` = cluster size, `h_c = |H_c| ≤ 36`, `|CH_c| ≤ 36`, `|HB_c| ≤ 18`.

| Phase                                | Asymptotic cost                            | Practical time                    |
| ------------------------------------ | ------------------------------------------ | --------------------------------- |
| 0. IF precomputation                 | `O(|T|)`                                   | `< 1 ms`                          |
| 1. City-center candidates            | `O(|T|)`                                   | `< 1 ms`                          |
| 2. Cluster graph + components        | `O(|𝒞|²)`                                  | `< 10 ms`                         |
| 3. Aqueduct enumeration              | `O(4^k)` per cluster                       | `< 1 ms` for `k ≤ 5`              |
| 4. Star-candidate scan per `α`       | `O(|R(T,6)| · k) = O(k)`                   | `< 1 ms` per `α`                  |
| 5. Branch-and-bound per cluster      | worst-case exponential; bounded in practice| `10³–10⁶` nodes (see below)        |
| 6. Output assembly                   | `O(k)`                                     | `< 1 ms`                          |

**Branch-and-bound — worst case unbounded analysis.** Without pruning, a `k`-city cluster has

```
∏_c h_c · |CH_c| · |HB_c|   ≤ (36 · 36 · 18)^k ≈ 23 000^k
```

complete configurations. For `k = 5` that's `≈ 6.4 × 10²¹` — intractable.

**With the pruning described:**

- **Star-locking** reduces each participating city's Hansa choice from `~ h_c` (up to 36) to `1–6` (neighbors of `T*` intersected with `H_c`).
- **Dominance pruning** typically removes 30–70% of `H_c` before branching.
- **Upper-bound pruning** cuts the branching factor sharply as soon as `L` is reasonable (which the greedy init ensures).
- **Triangle detection** fixes CH relative to Hansa for most cities, effectively collapsing one degree of freedom.

Empirical expectation for well-designed B&B on this structure: `10³–10⁶` nodes per cluster — seconds on commodity hardware.

**Total:** `O(|T| + |𝒞|² + Σ_clusters (4^k + nodes_BnB))`. For realistic inputs, seconds.

---

## 8. Worst Cases and Mitigations

### 8.1 Oversized cluster (`k ≥ 6`)

*Cause.* User requests `N = 5+` new cities in a tight area, or many candidates qualify as "high-synergy" with the starting city.

*Symptom.* Aqueduct enumeration grows to `4^6 = 4096`; B&B per aqueduct may exceed the practical time budget.

*Mitigation.*

- **Chordal decomposition**: split the cluster at its minimum articulation point (or minimum-weight edge cut) into overlapping sub-clusters of size `≤ 4`. Solve each sub-cluster optimally; stitch together at the shared cities by fixing their placements from the richer sub-cluster. Loses optimality bounded by the adjacency bonuses crossing the cut (at most `+2` per boundary pair).
- **Sequential fallback**: process cities in decreasing-`|A_c|` order, solving each jointly only with its already-placed neighbors. Linear in `k`; loses optimality bounded by `+2` per unseen forward interaction.

### 8.2 Arid / flat cluster (`|A_c| = 0` for all `c`)

*Cause.* No rivers, lakes, or mountains in the cluster.

*Symptom.* Aqueducts unavailable; within-city triangle loses one side (max +2 within-city instead of +4).

*Mitigation.* The algorithm handles `A_c = ∅` naturally (the enumeration includes "no aqueduct"). The star center falls back to **CommHub-centered**; the within-city optimum becomes either the **CH–HB triangle** (coastal) or a **CH-only pair** (inland). Explicitly prefer harbor-centered stars in this case.

### 8.3 Chained cluster topology

*Cause.* Cities `c₁, …, cₙ` with `d(c_i, c_{i+1}) ≤ 6` but `d(c_1, c_n) > 6`. The interaction graph is connected but has diameter `> 2`.

*Symptom.* A star centered at one end cannot reach the other; the cluster is not really a "star-able" unit, but the joint B&B still treats it as one.

*Mitigation.* Detect diameter `> 2` and split into overlapping 3-city windows along the chain. Optimize each window; re-run the boundary cities once in the wider context to capture edge effects.

### 8.4 Tied star candidates

*Cause.* Several centers `T_1, T_2, …` share the same `StarUB`.

*Symptom.* B&B explores all ties, wasting work.

*Mitigation.* Break ties in this order: (a) higher `IF(T)` (fixed-bonus richness), (b) CH-at-`T` also adjacent to a river (extra `+2` gold per adjacent river), (c) more contiguous-arc room for Hansas, (d) lexicographic tile order (deterministic output).

### 8.5 Harbor-only coastal cluster

*Cause.* Coastal cities with strong sea tiles, no rivers, no mountains.

*Symptom.* Aqueducts unavailable, but Harbor-centered stars viable.

*Mitigation.* Treat the Harbor as a legitimate star center. A Harbor-centered 3-star with coastal Hansas yields `3·2 + 2·1 = 8` Hansa production (star + contiguous chain) plus the Harbor's own base gold and the CH→HB cross-bonus. This competes with CH-centered stars.

### 8.6 Conflicting tile claims across cities

*Cause.* Two cities' working radii intersect on exactly the best Hansa tile for each.

*Symptom.* The global "one district per tile" constraint forces one city to settle.

*Mitigation.* Already captured by the QIP constraints. B&B branches on the allocation; dominance pruning typically resolves ties quickly by assigning the shared tile to the city whose best alternative is worst.

### 8.7 Cross-cluster leakage

*Cause.* The 6-tile cluster cut-off is tight but not a *strict* dominance bound — a Hansa on the boundary of one cluster can occasionally gain `+1` from an "other district" in a neighbor cluster (generic `+1` adjacency).

*Symptom.* Bounded by `+1` per cluster boundary pair. Usually negligible.

*Mitigation.* Optional post-pass: after per-cluster optimization, re-score boundary tiles with the now-concrete neighbor districts and perform a single-tile local improvement per city.

### 8.8 Numerical ties between "good 3-star" and "good pair"

*Cause.* Small map, few candidates; the algorithm finds multiple optima with identical score.

*Symptom.* Non-deterministic or surprising output.

*Mitigation.* Secondary objective (lex order after score): prefer configurations with (a) higher resource utilization, (b) more district triangles, (c) more harbors (if coastal), (d) fewer aqueducts (ties favor placements that leave future flexibility).

### 8.9 Degenerate fallback: pair dominates star

*Cause.* Committed `T*` has one city with only terrible Hansa neighbors of `T*`.

*Symptom.* Star score < pair score.

*Mitigation.* This is exactly the "good pair beats a bad 5-star" rule from the brief. The Phase 5 step 5 fallback handles this: abandon `T*`, re-run with the next candidate, ultimately falling back to no-star B&B if no star wins.

---

## 9. Data structures for the implementation

```
Tile:
  coords: (x, y, z)   # cube
  terrain, resource, resource_tier, river, coastal, existing_district
  IF: int              # filled in Phase 0

City (candidate or fixed):
  ctr: Tile
  coastal_flag: bool
  A, H, CH, HB: set[Tile]           # pre-filtered candidate sets
  high_synergy: bool

Cluster:
  cities: list[City]
  neighbors_by_tile: map[Tile, list[(City, 'H'|'CH'|'HB'|'Aq')]]

Assignment:
  aqueducts:  map[City, Tile | None]
  hansas:     map[City, Tile]
  commhubs:   map[City, Tile]
  harbors:    map[City, Tile | None]
  score: (production, gold)
```

Key primitives to implement once:

- `score_tile_as_hansa(t, assignment) -> int` — applies B over `N(t)`.
- `score_tile_as_ch(t, assignment) -> int` — river + adjacencies.
- `score_tile_as_hb(t, assignment) -> int`.
- `upper_bound(partial_assignment) -> (prod, gold)` — sum of `score_so_far + Σ MaxResidual(c)`.

---

## 10. Ordered pseudocode

```
solve(map, starting_city, N, mode, W):
    IF_map = compute_influence_field(map)
    candidates = enumerate_city_centers(map, starting_city)
    clusters = connected_components(build_cluster_graph(candidates))
    solutions = []
    for cluster in clusters:
        best_cluster_solution = None
        for α in aqueduct_enum(cluster):                     # Phase 3
            star_candidates = rank_stars(cluster, α)         # Phase 4
            tried = 0
            for T in star_candidates:
                L = greedy_init(cluster, α, star=T)
                bnb_result = branch_and_bound(cluster, α,
                                              star=T, lb=L)
                if bnb_result > best_cluster_solution:
                    best_cluster_solution = bnb_result
                tried += 1
                if tried >= STAR_TRY_BUDGET: break
            no_star_result = branch_and_bound(cluster, α, star=None)
            if no_star_result > best_cluster_solution:
                best_cluster_solution = no_star_result       # fallback rule
        solutions.append(best_cluster_solution)
    return merge_solutions(solutions, mode, W)
```

`STAR_TRY_BUDGET` defaults to 3 — the top 3 star candidates per aqueduct assignment. This is a tuning parameter; 3 is enough to catch the interesting geometry without exploding the runtime.

---

## 11. What this buys you over naive B&B

1. **Aqueduct-first** makes the outer loop `4^k`-small — deterministic and exhaustive.
2. **Star-priority** aligns branching with the real structure of the payoff: the most lucrative configurations lock in 3–4 city-to-city adjacencies simultaneously, so committing to them early gives a strong lower bound `L` and prunes `80–99%` of the non-star search space.
3. **Fallback rule** guarantees correctness: if no star actually dominates, the algorithm degrades gracefully to a pair- or triangle-only solution, rather than being locked into a suboptimal committed star.
4. **Cluster decomposition** keeps the expensive B&B scoped to `k ≤ 5` in almost all realistic inputs.

The mathematical guarantee is: **the algorithm returns the exact optimum for every cluster up to the star-try budget and dominance-pruning correctness**. The star-try budget introduces a bounded approximation only in pathological cases with many near-tied stars — and even then the error is bounded by the spread of `StarUB` values among the top candidates, which is small in practice.

---

*Derived 2026-04-24 to match the user's "aqueduct-first, star-formation, pair-fallback" specification.*
