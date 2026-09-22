"""Architectural diversity distance metric and duplicate detection.

Implements an interpretable, structural diversity metric based on architectural
graphs, circulation topology, zoning patterns, and proportion buckets.
"""

from __future__ import annotations
from typing import Set, Tuple
from app.models.alternatives import DesignSignature


def calculate_diversity_distance(sig1: DesignSignature, sig2: DesignSignature) -> float:
    """Calculate structural architectural diversity distance between two DesignSignatures.

    Returns a normalized value in [0.0, 1.0]:
      0.0: Identical architectural structures (near-duplicate or exact duplicate).
      1.0: Completely divergent architectural organization across all dimensions.

    Args:
        sig1: First DesignSignature.
        sig2: Second DesignSignature.

    Returns:
        Interpretable diversity distance in [0.0, 1.0].
    """
    # 1. Adjacency graph Jaccard distance (weight: 0.35)
    edges1 = set(sig1.adjacency_edges)
    edges2 = set(sig2.adjacency_edges)
    union_edges = edges1.union(edges2)
    if not union_edges:
        adj_dist = 0.0
    else:
        inter_edges = edges1.intersection(edges2)
        adj_dist = 1.0 - (len(inter_edges) / len(union_edges))

    # 2. Circulation topology distance (weight: 0.15)
    if sig1.circulation_type == sig2.circulation_type:
        circ_dist = 0.0
    elif "hybrid" in sig1.circulation_type or "hybrid" in sig2.circulation_type:
        circ_dist = 0.5
    else:
        circ_dist = 1.0

    # 3. Social sequence distance (weight: 0.15)
    seq1 = list(sig1.social_sequence)
    seq2 = list(sig2.social_sequence)
    if seq1 == seq2:
        seq_dist = 0.0
    elif set(seq1) == set(seq2):
        seq_dist = 0.5
    else:
        seq_dist = 1.0

    # 4. Zoning, Entrance, and Staircase relationship distance (weight: 0.15)
    ent_diff = 0.0 if sig1.entrance_room_type == sig2.entrance_room_type else 1.0
    priv_diff = 0.0 if sig1.private_clustering == sig2.private_clustering else 1.0
    stair_diff = 0.0 if sig1.staircase_relationship == sig2.staircase_relationship else 1.0
    zoning_dist = (ent_diff + priv_diff + stair_diff) / 3.0

    # 5. Room shapes and proportion buckets distance (weight: 0.20)
    shapes1 = dict(sig1.room_shapes)
    shapes2 = dict(sig2.room_shapes)
    all_rooms = set(shapes1.keys()).union(set(shapes2.keys()))
    if not all_rooms:
        shape_dist = 0.0
    else:
        diff_count = sum(1 for r in all_rooms if shapes1.get(r) != shapes2.get(r))
        shape_dist = diff_count / len(all_rooms)

    props1 = dict(sig1.proportion_buckets)
    props2 = dict(sig2.proportion_buckets)
    all_prop_rooms = set(props1.keys()).union(set(props2.keys()))
    if not all_prop_rooms:
        prop_dist = 0.0
    else:
        diff_prop_count = sum(1 for r in all_prop_rooms if props1.get(r) != props2.get(r))
        prop_dist = diff_prop_count / len(all_prop_rooms)

    form_dist = (shape_dist + prop_dist) / 2.0

    # Weighted aggregate distance
    total_dist = (
        0.35 * adj_dist +
        0.15 * circ_dist +
        0.15 * seq_dist +
        0.15 * zoning_dist +
        0.20 * form_dist
    )

    return round(min(1.0, max(0.0, total_dist)), 4)


def is_duplicate(sig1: DesignSignature, sig2: DesignSignature) -> bool:
    """Check if two signatures are structurally identical duplicates."""
    return calculate_diversity_distance(sig1, sig2) == 0.0


def is_near_duplicate(
    sig1: DesignSignature,
    sig2: DesignSignature,
    minimum_diversity_distance: float = 0.25,
) -> bool:
    """Check if two signatures are near-duplicates below the required diversity distance."""
    return calculate_diversity_distance(sig1, sig2) < minimum_diversity_distance
