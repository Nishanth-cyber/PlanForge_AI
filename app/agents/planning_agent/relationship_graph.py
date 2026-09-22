"""Relationship Graph Builder — manages 4-tier architectural relationships.

Relationship tiers:
1. REQUIRED ADJACENCY:  Explicitly specified by user (e.g. Living next to Dining).
2. PREFERRED ADJACENCY: Standard architectural patterns (e.g. Kitchen near Dining, Foyer near Living).
3. SEPARATION (AVOID):  Required distance/isolation (e.g. Garage away from Bedroom, Ensuite avoiding Living).
4. ATTACHED:            Direct parent-suite coupling (e.g. Ensuite attached to Master Bedroom).

Guarantees:
- Bidirectional symmetry (if A is adjacent to B, B is adjacent to A).
- No duplicate edges or self-loops.
- Conflict resolution (Avoid/Separation strictly overrides default Preferred Adjacency).
"""

from __future__ import annotations

from typing import Iterable, Optional
from app.models.planning import RoomSpec


# Default architectural preferred adjacency pairs (symmetric)
DEFAULT_PREFERRED_ADJACENCIES: list[tuple[str, str]] = [
    ("living", "dining"),
    ("dining", "kitchen"),
    ("living", "foyer"),
    ("kitchen", "utility"),
    ("kitchen", "storage"),
    ("kitchen", "pantry"),
    ("bedroom", "bathroom"),
    ("master_bedroom", "bathroom"),
    ("living", "porch"),
    ("living", "balcony"),
]

# Standard architectural avoidance / separation pairs (symmetric)
DEFAULT_AVOID_PAIRS: list[tuple[str, str]] = [
    ("garage", "bedroom"),
    ("garage", "master_bedroom"),
    ("garage", "kitchen"),
    ("attached_bathroom", "living"),
    ("attached_bathroom", "dining"),
    ("attached_bathroom", "kitchen"),
]


class RelationshipGraphBuilder:
    """Builds consistent, normalized relationship graphs for floor-level planning."""

    @classmethod
    def build_matrices(
        cls,
        room_specs: list[RoomSpec],
        explicit_adjacencies: Optional[dict[str, list[str]]] = None,
        explicit_avoids: Optional[dict[str, list[str]]] = None,
        attached_pairs: Optional[list[tuple[str, str]]] = None,
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Build normalized adjacency and avoid matrices for a list of planned rooms on a floor.

        Args:
            room_specs:           List of RoomSpec instances on this floor.
            explicit_adjacencies: Optional mapping of room_type -> list of adjacent room_types.
            explicit_avoids:      Optional mapping of room_type -> list of avoided room_types.
            attached_pairs:       Optional list of (parent_room_type, attached_room_type) pairs.

        Returns:
            Tuple of (adjacency_matrix, avoid_matrix).
        """
        room_types = {r.room_type for r in room_specs if r.room_type}
        adj_graph: dict[str, set[str]] = {rt: set() for rt in room_types}
        avoid_graph: dict[str, set[str]] = {rt: set() for rt in room_types}

        # 1. Register attached pairs (strongest adjacency)
        if attached_pairs:
            for parent, child in attached_pairs:
                if parent in room_types and child in room_types and parent != child:
                    adj_graph[parent].add(child)
                    adj_graph[child].add(parent)

        # 2. Register explicit required adjacencies from user
        if explicit_adjacencies:
            for r_type, targets in explicit_adjacencies.items():
                if r_type not in room_types:
                    continue
                for t in targets:
                    if t in room_types and t != r_type:
                        adj_graph[r_type].add(t)
                        adj_graph[t].add(r_type)

        # Also pull from individual RoomSpec.adjacency
        for r in room_specs:
            for t in r.adjacency:
                if t in room_types and t != r.room_type:
                    adj_graph[r.room_type].add(t)
                    adj_graph[t].add(r.room_type)

        # 3. Register explicit avoids from user
        if explicit_avoids:
            for r_type, targets in explicit_avoids.items():
                if r_type not in room_types:
                    continue
                for t in targets:
                    if t in room_types and t != r_type:
                        avoid_graph[r_type].add(t)
                        avoid_graph[t].add(r_type)

        # Also pull from individual RoomSpec.avoid
        for r in room_specs:
            for t in r.avoid:
                if t in room_types and t != r.room_type:
                    avoid_graph[r.room_type].add(t)
                    avoid_graph[t].add(r.room_type)

        # 4. Apply default avoidance rules (e.g. garage avoids bedrooms)
        for a, b in DEFAULT_AVOID_PAIRS:
            if a in room_types and b in room_types and a != b:
                # Do not add avoid if user explicitly required adjacency!
                if b not in adj_graph[a]:
                    avoid_graph[a].add(b)
                    avoid_graph[b].add(a)

        # 5. Apply default preferred adjacencies (only if not avoiding)
        for a, b in DEFAULT_PREFERRED_ADJACENCIES:
            if a in room_types and b in room_types and a != b:
                if b not in avoid_graph[a] and a not in avoid_graph[b]:
                    adj_graph[a].add(b)
                    adj_graph[b].add(a)

        # 6. Ensure conflict resolution: Avoid strictly clears Adjacency
        for rt in room_types:
            conflicts = adj_graph[rt].intersection(avoid_graph[rt])
            for c in conflicts:
                adj_graph[rt].discard(c)
                adj_graph[c].discard(rt)

        # 7. Format sorted, deterministic dicts
        adjacency_matrix: dict[str, list[str]] = {
            rt: sorted(list(neighbors)) for rt, neighbors in adj_graph.items()
        }
        avoid_matrix: dict[str, list[str]] = {
            rt: sorted(list(avoids)) for rt, avoids in avoid_graph.items()
        }

        return adjacency_matrix, avoid_matrix
