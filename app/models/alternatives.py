"""Data models for architectural diversity and multi-design alternatives.

Captures design strategies, alternative statuses, structural design signatures,
individual design alternatives, and the complete multi-alternative set.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.refinement import RefinementResult
from app.models.validation import ValidationReport
from app.utils.ids import generate_id


class DesignStrategy(str, Enum):
    """Authoritative architectural design strategies for diversity exploration."""
    SOCIAL_CENTRIC = "social_centric"
    CORRIDOR_CENTRIC = "corridor_centric"
    COMPACT_CIRCULATION = "compact_circulation"
    PRIVACY_CENTRIC = "privacy_centric"
    OPEN_SOCIAL = "open_social"
    SERVICE_CLUSTERED = "service_clustered"


class AlternativeStatus(str, Enum):
    """Lifecycle and qualification status of a candidate alternative."""
    GENERATED = "generated"
    VALIDATED = "validated"
    REFINED_AND_VALID = "refined_and_valid"
    INVALID = "invalid"
    FAILED_VALIDATION = "failed_validation"
    DUPLICATE = "duplicate"
    INSUFFICIENT_DIVERSITY = "insufficient_diversity"
    REFINEMENT_FAILED = "refinement_failed"
    REJECTED = "rejected"


class RejectionReason(str, Enum):
    """Structured architectural rejection reasons."""
    SCHEMA_FAILURE = "schema_failure"
    GEOMETRY_FAILURE = "geometry_failure"
    VALIDATION_FAILURE = "validation_failure"
    REFINEMENT_FAILED = "refinement_failed"
    DUPLICATE = "duplicate"
    INSUFFICIENT_DIVERSITY = "insufficient_diversity"
    INVARIANT_VIOLATION = "invariant_violation"


@dataclass(frozen=True)
class DesignSignature:
    """Deterministic structural architectural diversity representation.
    
    Normalizes away arbitrary entity IDs, timestamps, and order, focusing on
    meaningful architectural organization: adjacency, circulation, zoning,
    proportions, and shapes.
    """
    adjacency_edges: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    circulation_type: str = "direct"
    entrance_room_type: str = "living"
    social_sequence: Tuple[str, ...] = field(default_factory=tuple)
    private_clustering: str = "clustered"
    staircase_relationship: str = "none"
    room_shapes: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    proportion_buckets: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        """Convert signature to serialized dictionary."""
        return {
            "adjacency_edges": [list(edge) for edge in self.adjacency_edges],
            "circulation_type": self.circulation_type,
            "entrance_room_type": self.entrance_room_type,
            "social_sequence": list(self.social_sequence),
            "private_clustering": self.private_clustering,
            "staircase_relationship": self.staircase_relationship,
            "room_shapes": dict(self.room_shapes),
            "proportion_buckets": dict(self.proportion_buckets),
        }


@dataclass
class DesignAlternative:
    """A single residential architectural alternative."""
    alternative_id: str
    index: int
    strategy: str
    architectural_design: Optional[ArchitecturalDesignSet] = None
    floor_plan_set: Optional[FloorPlanSet] = None
    validation_report: Optional[ValidationReport] = None
    refinement_result: Optional[RefinementResult] = None
    design_signature: Optional[DesignSignature] = None
    diversity_scores: Dict[str, float] = field(default_factory=dict)
    status: AlternativeStatus = AlternativeStatus.GENERATED
    rejection_reason: Optional[str] = None
    design_rationale: str = ""
    characteristics: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if alternative is certified as valid."""
        return self.status in (AlternativeStatus.VALIDATED, AlternativeStatus.REFINED_AND_VALID)


@dataclass
class DesignAlternativeSet:
    """Container for the set of validated diverse architectural alternatives."""
    id: str = field(default_factory=generate_id)
    project_name: str = ""
    requested_count: int = 3
    candidates_generated: int = 0
    alternatives: List[DesignAlternative] = field(default_factory=list)
    rejected_candidates: List[DesignAlternative] = field(default_factory=list)
    strategies_attempted: List[str] = field(default_factory=list)
    status: str = "COMPLETE"
    generation_summary: str = ""

    @property
    def valid_count(self) -> int:
        """Count of accepted valid alternatives."""
        return len(self.alternatives)

    @property
    def rejected_count(self) -> int:
        """Count of rejected candidate alternatives."""
        return len(self.rejected_candidates)
