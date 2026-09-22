"""Design Signature extraction and canonical normalization for architectural diversity.

Computes a deterministic, normalized structural fingerprint of an architectural design,
focusing on spatial connectivity, circulation topology, zoning sequence, room shapes,
and proportion buckets, while normalizing away IDs, timestamps, and transient geometry.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple
from app.models.alternatives import DesignSignature
from app.models.architectural_design import ArchitecturalDesignSet, RoomDesign


class DesignSignatureBuilder:
    """Extracts a normalized DesignSignature from an ArchitecturalDesignSet."""

    @staticmethod
    def build(design_set: ArchitecturalDesignSet) -> DesignSignature:
        """Construct deterministic DesignSignature from an ArchitecturalDesignSet.

        Args:
            design_set: The architectural design set to analyze.

        Returns:
            Normalized, immutable DesignSignature.
        """
        adjacency_set: Set[Tuple[str, str]] = set()
        entrance_room = "living"
        circulation_counts = {"corridor": 0, "direct": 0}
        social_sequence_list: List[str] = []
        staircase_rel = "none"

        # Collect rooms across all floors
        all_rooms: List[RoomDesign] = []
        for floor_design in design_set.designs:
            all_rooms.extend(floor_design.rooms)

            # Analyze staircase relationship
            if floor_design.staircase_intent:
                staircase_rel = "circulation_core"

        # Build type and connection maps
        room_types = {r.id: r.room_type for r in all_rooms}

        for r in all_rooms:
            rt = r.room_type

            for d in r.doors:
                connects_to = d.connects_to.strip().lower() if d.connects_to else "circulation"

                # Check for entrance
                if d.door_type == "entrance" or connects_to == "exterior":
                    entrance_room = rt

                # Classify connection type
                if connects_to in ("circulation", "corridor", "hallway", "foyer"):
                    circulation_counts["corridor"] += 1
                else:
                    circulation_counts["direct"] += 1

                # Normalize target name if it references a room ID
                target_type = room_types.get(connects_to, connects_to)

                # Canonical sorted pair
                edge = tuple(sorted([rt, target_type]))
                adjacency_set.add((edge[0], edge[1]))

        # Determine circulation type
        corr_count = circulation_counts["corridor"]
        dir_count = circulation_counts["direct"]
        if corr_count > 0 and dir_count == 0:
            circulation_type = "corridor"
        elif dir_count > 0 and corr_count == 0:
            circulation_type = "direct"
        elif corr_count >= dir_count:
            circulation_type = "hybrid_corridor"
        else:
            circulation_type = "hybrid_direct"

        # Analyze social sequence
        # Check standard social rooms
        social_rooms_present = [r.room_type for r in all_rooms if r.room_type in ("living", "dining", "kitchen")]
        if ("dining", "living") in adjacency_set or ("living", "dining") in adjacency_set:
            if ("dining", "kitchen") in adjacency_set or ("kitchen", "dining") in adjacency_set:
                social_sequence_list = ["living", "dining", "kitchen"]
            else:
                social_sequence_list = ["living", "dining"]
        elif ("circulation", "living") in adjacency_set and ("circulation", "dining") in adjacency_set:
            social_sequence_list = ["living", "corridor", "dining"]
        else:
            social_sequence_list = sorted(list(set(social_rooms_present)))

        # Private clustering
        private_rooms = [r for r in all_rooms if "bedroom" in r.room_type or r.room_type in ("bedroom", "master_bedroom", "guest_bedroom")]
        attached_count = sum(1 for r in all_rooms if r.doors and any(d.connects_to == "parent_suite" for d in r.doors))
        if attached_count > 0:
            private_clustering = "suite_buffered"
        elif len(private_rooms) > 1:
            private_clustering = "clustered"
        else:
            private_clustering = "standard"

        # Room shapes (canonical sorted)
        shapes: Dict[str, str] = {}
        proportions: Dict[str, str] = {}
        for r in all_rooms:
            rt = r.room_type
            shape = r.intended_shape or "rectangular"
            shapes[rt] = shape

            # Proportion bucket
            if r.intended_dimensions and len(r.intended_dimensions) == 2:
                w, l = r.intended_dimensions[0], r.intended_dimensions[1]
                min_dim = min(w, l)
                max_dim = max(w, l)
                aspect = max_dim / min_dim if min_dim > 0 else 1.0

                if aspect <= 1.15 or shape == "square":
                    bucket = "square"
                elif aspect <= 1.5:
                    bucket = "standard"
                else:
                    bucket = "elongated"
            else:
                bucket = "standard"
            proportions[rt] = bucket

        sorted_edges = tuple(sorted(list(adjacency_set)))
        sorted_shapes = tuple(sorted(shapes.items()))
        sorted_props = tuple(sorted(proportions.items()))

        return DesignSignature(
            adjacency_edges=sorted_edges,
            circulation_type=circulation_type,
            entrance_room_type=entrance_room,
            social_sequence=tuple(social_sequence_list),
            private_clustering=private_clustering,
            staircase_relationship=staircase_rel,
            room_shapes=sorted_shapes,
            proportion_buckets=sorted_props,
        )
