# PlanForge — Multi-Design Generation & Architectural Diversity (Phase 9)

This document provides the comprehensive architecture, design rationale, and formal specifications for **Phase 9: Multi-Design Generation & Architectural Diversity** in the PlanForge AI residential generative floor-planning system.

---

## 1. Architectural Overview & Purpose

In automated residential floor planning, generating multiple floor-plan alternatives is an essential feature for homeowners, developers, and architects. However, conventional generative systems often produce "pseudo-diversity":
- Shifting a window by a few centimeters,
- Adding small random coordinate jitter to wall endpoints,
- Inverting a door swing without changing the circulation topology, or
- Arbitrarily dropping rooms or violating minimum area constraints to fit an ad-hoc layout.

Such trivial variations do not represent distinct architectural design decisions. True architectural diversity manifests in:
1. **Spatial Experience & Flow**: How rooms relate to one another (e.g., direct open connections vs. hallway buffers).
2. **Circulation Topology**: Whether the house relies on a central spine, a compact direct-access matrix, or a buffered privacy-oriented layout.
3. **Zoning & Privacy**: How public entertaining spaces are sequestered from private sleeping quarters.
4. **Spatial Geometry & Proportions**: Semantic room shapes (square vs. elongated rectangular) within assigned spatial envelopes.

Phase 9 establishes the `MultiDesignGenerator` and diversity measurement engine in PlanForge AI, enabling the generation of multiple, verified, structurally diverse residential floor plans from a single user brief and ASAA spatial allocation.

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 User Brief + Requirements              │
                  └───────────────────────────┬────────────────────────────┘
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │            Planning Agent (PlanningSpec)               │
                  └───────────────────────────┬────────────────────────────┘
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │          ASAA Spatial Allocator (AllocationSet)        │
                  │             (Spatial Bounding Envelopes Locked)        │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      │ Strategy 1: Social-Centric                    │
                      │ Strategy 2: Corridor-Centric                  │
                      │ Strategy 3: Compact Circulation               │
                      │ Strategy 4: Privacy-Centric                   │
                      │ Strategy 5: Open Social                       │
                      │ Strategy 6: Service Clustered                 │
                      └───────────────────────┬───────────────────────┘
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │          Architectural LLM Agent              │
                      │    (Proposes RoomDesign, Doors, Windows)      │
                      └───────────────────────┬───────────────────────┘
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │          Geometry Engine (Phase 6)            │
                      │    (Builds Physical Walls, Doors, Rooms)      │
                      └───────────────────────┬───────────────────────┘
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │          FloorPlanValidator (Phase 7)         │
                      │             (18 Deterministic Checks)         │
                      └───────────────────────┬───────────────────────┘
                                              │ (If invalid)
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │           RefinementLoop (Phase 8)            │
                      │    (Iterative Rule-Based Error Repair)        │
                      └───────────────────────┬───────────────────────┘
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │       Structural DesignSignature Extractor    │
                      │      (Adjacency, Circulation, Shapes, Proportions)  │
                      └───────────────────────┬───────────────────────┘
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │         Pairwise Diversity Evaluator          │
                      │    (Filters Duplicates & Near-Duplicates)     │
                      └───────────────────────┬───────────────────────┘
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │            DesignAlternativeSet               │
                      │    (All Valid, Diverse, Audited Candidates)   │
                      └───────────────────────────────────────────────┘
```

---

## 2. Invariants & Guardrails

Phase 9 strictly adheres to the following system invariants:

1. **ASAA Allocation Immutability**:
   All alternatives generated for a project operate within the *same* `AllocationSet`. A room cannot change its assigned region polygon or jump to an unallocated zone. Diversity is explored in how spaces are organized, connected, and shaped *within* their allocated envelopes.
2. **100% Requirement Preservation**:
   Room counts, room identities, floor counts, floor assignments, and minimum required areas are preserved across every alternative without exception. No candidate may invent or drop rooms to achieve validity or diversity.
3. **Zero Raw Geometry Output from LLM**:
   The LLM agent operates strictly at the architectural intent layer (`RoomDesign`, `DoorIntent`, `WindowIntent`). All physical geometry (`GeoRoom`, `GeoWall`, `GeoDoor`, `GeoWindow`, `GeoStaircase`) is constructed by the deterministic `GeometryEngine`.
4. **Independent Validation & Zero Self-Certification**:
   No candidate alternative is accepted into the final output without passing `FloorPlanValidator.overall_valid == True`. Candidates that initially fail are sent through the `RefinementLoop`. Candidates that fail validation after refinement are rejected with a structured `RejectionReason.VALIDATION_FAILURE`.
5. **No "Best Design" Claims**:
   The generator produces alternatives with transparent structural characteristics, design strategies, validation scores, and pairwise diversity distances. It does not rank or claim one layout is universally superior to another.

---

## 3. Architectural Design Strategies

To drive meaningful structural differences rather than random permutations, PlanForge explores six distinct architectural strategies:

| Strategy | Spatial Focus | Door / Connectivity Pattern | Circulation Flow |
|---|---|---|---|
| `social_centric` | Maximizes entertaining flow between public zones | Direct Living $\leftrightarrow$ Dining $\leftrightarrow$ Kitchen links | Fluid, interconnected entertaining zone; private wing buffered |
| `corridor_centric` | Maximizes acoustic separation and structured flow | All rooms open independently into a central corridor | Clean hierarchical spine; zero room-through-room traffic |
| `compact_circulation` | Minimizes hallway area; efficient modern living | Direct room-to-room transitions; integrated circulation | Minimal corridor footprint; immediate room adjacencies |
| `privacy_centric` | Maximizes seclusion of private bedrooms and study | Formal living buffer; secluded private hallway | Segmented public/private zones; deep privacy buffer |
| `open_social` | Open-plan modern residential concept | Wide double doors; unified living-dining-kitchen vista | Expansive open sightlines and generous portals |
| `service_clustered` | Utilitarian efficiency | Kitchen, laundry, powder room, and utilities clustered | Consolidated plumbing and acoustic service cores |

---

## 4. The Canonical Structural Signature (`DesignSignature`)

To quantitatively evaluate whether two candidate floor plans are structurally different, PlanForge extracts a `DesignSignature` from each candidate's validated `ArchitecturalDesignSet`.

```python
@dataclass(frozen=True)
class DesignSignature:
    adjacency_edges: tuple[tuple[str, str], ...]      # Canonical sorted unique connected pairs
    circulation_type: str                            # 'open_plan', 'central_spine', 'compact_hub', etc.
    entrance_room_type: str                          # Room type receiving main entrance
    social_sequence: tuple[str, ...]                 # Order of public spaces from entry
    private_clustering: str                          # 'clustered', 'dispersed', 'isolated'
    staircase_relationship: str                      # Spatial relationship to vertical core
    room_shapes: tuple[tuple[str, str], ...]         # Semantic shapes per room type
    proportion_buckets: tuple[tuple[str, str], ...]  # 'square', 'standard', 'elongated'
```

### Signature Components

1. **Normalized Adjacency Edges**:
   Extracted from realized interior and entrance doors. For every door connecting room $A$ and room $B$, the pair is sorted alphabetically: `(min(type_A, type_B), max(type_A, type_B))`. The full edge set is deduplicated and sorted, forming an invariant topological connectivity graph.
2. **Circulation Type**:
   Classified based on graph degree distribution and hallway linkages:
   - `open_plan`: Direct interconnected social spaces without dedicated hallway.
   - `central_spine`: Corridor has high degree connecting $\ge 4$ spaces.
   - `compact_hub`: Localized direct transitions with minimal circulation zones.
   - `hybrid_corridor`: Mixed direct linkages and corridor segments.
3. **Entrance Room Type**:
   The functional room receiving the primary exterior entrance door (e.g., `living`, `foyer`, `dining`).
4. **Social Sequence**:
   The sequential traversal order of public living areas starting from the main entrance door.
5. **Private Clustering**:
   Measures whether private spaces (bedrooms, bathrooms) share common boundaries (`clustered`) or are separated by social/circulation zones (`dispersed`).
6. **Staircase Relationship**:
   The functional zone directly providing access to the vertical staircase core (`foyer`, `living`, `corridor`, `none`).
7. **Room Shapes**:
   Semantic geometric shapes (`rectangular`, `square`, `l_shaped`) per room.
8. **Proportion Buckets**:
   Categorization of aspect ratio ($L / W$):
   - `square`: Aspect ratio $\le 1.15$.
   - `standard`: $1.15 < \text{ratio} \le 1.60$.
   - `elongated`: $\text{ratio} > 1.60$.

---

## 5. Diversity Metric & Distance Calculation

PlanForge computes the pairwise diversity distance between two designs using a weighted multi-attribute distance metric:

$$D(A, B) = \sum_{k} w_k \cdot \delta_k(A, B)$$

Where:
- **Graph Adjacency Distance** ($\delta_{\text{adj}}$): Jaccard distance on normalized door-connectivity edge sets:
  $$\delta_{\text{adj}} = 1.0 - \frac{|E_A \cap E_B|}{|E_A \cup E_B|}$$
- **Circulation Distance** ($\delta_{\text{circ}}$): $0.0$ if identical circulation classification, $1.0$ if different.
- **Entrance Distance** ($\delta_{\text{ent}}$): $0.0$ if same entrance room, $1.0$ if different.
- **Social Sequence Distance** ($\delta_{\text{seq}}$): Normalized Levenshtein edit distance between public traversal sequences.
- **Private Clustering Distance** ($\delta_{\text{priv}}$): $0.0$ if identical clustering, $1.0$ if different.
- **Staircase Relationship Distance** ($\delta_{\text{stair}}$): $0.0$ if identical vertical core access, $1.0$ if different.
- **Shape Distance** ($\delta_{\text{shape}}$): Hamming distance over semantic room shape assignments.
- **Proportion Distance** ($\delta_{\text{prop}}$): Hamming distance over room aspect ratio buckets.

### Feature Weights ($w_k$)

| Feature | Weight ($w_k$) | Rationale |
|---|---|---|
| Adjacency Graph ($E$) | **0.40** | Direct topological connectivity is the primary driver of layout differentiation |
| Circulation Type | **0.20** | Spine vs. hub vs. open-plan fundamentally dictates user movement |
| Entrance Room | **0.10** | Welcoming experience and primary threshold sequence |
| Social Sequence | **0.10** | Order of entertainment and public zones |
| Private Clustering | **0.05** | Bedroom wing acoustics and separation |
| Staircase Core Access | **0.05** | Vertical navigation origin |
| Room Shapes | **0.05** | Architectural geometry (square vs. rectangular vs. L-shaped) |
| Room Proportions | **0.05** | Room aspect ratio and spatial feel |
| **Total** | **1.00** | Strictly normalized to $[0.0, 1.0]$ |

### Mathematical Properties

- **Range**: $D(A, B) \in [0.0, 1.0]$.
- **Identity of Indiscernibles**: $D(A, A) = 0.0$.
- **Symmetry**: $D(A, B) = D(B, A)$.
- **Triangle Inequality**: Satisfied over the feature space.

### Filtering Rules

- **Exact Duplicate**: $D(A, B) == 0.0$. The candidate is immediately rejected with `RejectionReason.DUPLICATE`.
- **Near-Duplicate / Insufficient Diversity**: $D(A, B) < \tau_{\text{div}}$ (default threshold $\tau_{\text{div}} = 0.15$). The candidate is rejected with `RejectionReason.INSUFFICIENT_DIVERSITY`.

---

## 6. Multi-Design Generator Orchestration

`MultiDesignGenerator` manages candidate budgeting, synthesis, validation, refinement, and packaging:

```python
alt_set: DesignAlternativeSet = generator.generate(
    planning_spec=planning_spec,
    allocation_set=allocation_set,
    requirements=requirements,
    num_alternatives=3,
    candidate_budget=6,
    minimum_diversity_distance=0.15,
    project_name="Meadowbrook Residence",
)
```

### Candidate Generation Loop

1. **Candidate Budgeting**: Attempts up to `candidate_budget` iterations (default: $2 \times \text{num\_alternatives}$, minimum 4).
2. **Strategy Selection**: Cycles systematically through `DesignStrategy` values (`social_centric`, `corridor_centric`, `compact_circulation`, `privacy_centric`, `open_social`, `service_clustered`).
3. **Intent Generation**: Invokes `ArchitecturalAgent.design(..., strategy=strat, alternative_index=idx)`.
4. **Invariant Checking**: Confirms 100% room preservation and ASAA region IDs.
5. **Physical Construction & Refinement**: Passes design to `RefinementLoop.run(..., target_strategy=strat)`.
6. **Validity Verification**: Verifies `refinement_result.is_valid == True`. Invalid candidates are logged with failure reasons.
7. **Signature Extraction**: Extracts canonical `DesignSignature`.
8. **Diversity Distance Filtering**: Evaluates distance against all previously accepted alternatives. Rejects duplicates or near-duplicates.
9. **Acceptance & Summary**: When `len(accepted) == num_alternatives` or the budget is exhausted, packages results into `DesignAlternativeSet`.

---

## 7. Research Audit Logging & Status Semantics

Every candidate generated during a run is recorded in the output `DesignAlternativeSet`:

- `alternatives`: List of accepted `DesignAlternative` instances, each containing:
  - `index`: 1-based sequential alternative number.
  - `strategy`: Architectural strategy employed.
  - `floor_plan_set`: Valid physical geometry.
  - `validation_report`: Complete validator report certifying `overall_valid == True`.
  - `refinement_result`: Refinement trajectory history and change records.
  - `design_signature`: Normalized structural signature.
  - `diversity_scores`: Distance to all other accepted alternatives.
  - `characteristics`: Human-readable architectural traits.
- `rejected_candidates`: Complete audit log of discarded candidates with structured `RejectionReason`:
  - `SCHEMA_FAILURE`: LLM output parsing failed.
  - `INVARIANT_VIOLATION`: Allocation ID or room count tampered.
  - `GEOMETRY_FAILURE`: Physical dimensions exceeded region envelope.
  - `VALIDATION_FAILURE`: Candidate failed independent validator checks.
  - `DUPLICATE`: Structurally identical to an accepted design ($d = 0.0$).
  - `INSUFFICIENT_DIVERSITY`: Below minimum diversity distance ($d < \tau_{\text{div}}$).

---

## 8. Verification & Test Coverage

Phase 9 is validated across a dedicated test suite verifying all mathematical and architectural invariants:

1. **Signature Normalization** (`test_design_signature.py`):
   - Adjacency edge sorting and canonical deduplication.
   - Classification of circulation types (spine, hub, open).
   - Staircase core attachment detection.
2. **Diversity Metrics** (`test_diversity_metrics.py`):
   - Symmetry: $d(A, B) = d(B, A)$.
   - Bounds: $0.0 \le d(A, B) \le 1.0$.
   - Near-duplicate detection: Candidates differing only by minor window placements receive $d < 0.05$ and are flagged as near-duplicates, while structurally distinct layouts achieve $d \ge 0.25$.
3. **Generator Coordination** (`test_multi_design_generator.py`):
   - Validity + Diversity filtering: Invalid candidates and duplicate candidates are rejected, while diverse valid candidates are accepted.
   - Budget exhaustion handling when diversity threshold cannot be met.
4. **Prompt Propagation & Immutability** (`test_strategy_prompt_propagation.py`, `test_refinement_diversity_preservation.py`):
   - Strategy prompt injection into both architectural design and refinement loops.
   - Preservation of target strategy during iterative error correction.
5. **End-to-End Pipeline Integration** (`test_diversity_generation.py`):
   - Single-floor family home producing 3 valid, verified alternatives with pairwise distances $\ge 0.15$.
   - Multi-floor villa generating distinct valid layouts while locking vertical staircase cores.
   - Irregular L-shaped plot diversity generation without bounding box fallback.
