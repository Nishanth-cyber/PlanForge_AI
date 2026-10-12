"""Phase 7: Interactive Agentic Clarification and Resumable Floor-Plan Generation.

Provides typed schemas, decision policies, grounded alternative generation,
response validation, and provenance records for interactive user clarification.
"""

from __future__ import annotations

import copy
import math
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from app.agentic.util import to_jsonable
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.utils.ids import generate_id


class ClarificationCategory(str, Enum):
    """Categorization of clarification decisions."""

    PROCEED = "PROCEED"
    CLARIFY = "CLARIFY"
    OFFER_ALTERNATIVES = "OFFER_ALTERNATIVES"
    REQUEST_CONSTRAINT_REVISION = "REQUEST_CONSTRAINT_REVISION"
    TERMINATE = "TERMINATE"


class AlternativeFeasibilityType(str, Enum):
    """Truthful classification of alternative feasibility status."""

    VERIFIED_FEASIBLE = "VERIFIED_FEASIBLE"
    SUGGESTED_ALTERNATIVE = "SUGGESTED_ALTERNATIVE"
    UNVERIFIED_HYPOTHETICAL = "UNVERIFIED_HYPOTHETICAL"


class ClarificationStatus(str, Enum):
    """Status lifecycle of a clarification request."""

    PENDING = "pending"
    ANSWERED = "answered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class ClarificationOption:
    """A concrete, selectable option presented to the user during clarification."""

    option_id: str
    label: str = ""
    title: str = ""
    description: str = ""
    proposed_changes: Dict[str, Any] = field(default_factory=dict)
    numeric_changes: Dict[str, float] = field(default_factory=dict)
    affected_rooms: List[str] = field(default_factory=list)
    feasibility_type: Union[AlternativeFeasibilityType, str] = AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE
    is_verified_feasible: bool = False
    requires_confirmation: bool = True
    grounded_evidence: Optional[str] = None
    action_type: str = "custom"  # "expand_plot", "add_floor", "scale_rooms", "remove_optional_room", "cancel"

    def __post_init__(self) -> None:
        if not self.title and self.label:
            self.title = self.label
        elif not self.label and self.title:
            self.label = self.title
        if not self.numeric_changes and self.proposed_changes:
            for k, v in self.proposed_changes.items():
                if isinstance(v, (int, float)):
                    self.numeric_changes[k] = float(v)

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class ClarificationRequest:
    """A structured request for user intervention when requirements are incomplete,
    ambiguous, contradictory, or infeasible.
    """

    request_id: str
    project_id: str
    state_version: int
    category: ClarificationCategory
    issue_explanation: str = ""
    question: str = ""
    evidence: str = ""
    supporting_evidence: List[Any] = field(default_factory=list)
    is_mandatory: bool = True
    suggested_options: List[ClarificationOption] = field(default_factory=list)
    options: List[ClarificationOption] = field(default_factory=list)
    default_behavior: Optional[str] = None
    affected_requirements: List[str] = field(default_factory=list)
    affected_constraints: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    paused_stage: str = "requirements"
    status: ClarificationStatus = ClarificationStatus.PENDING
    questions: List[str] = field(default_factory=list)
    measured_deficit_sqm: Optional[float] = None
    available_sqm: Optional[float] = None
    required_sqm: Optional[float] = None
    target_component: Optional[str] = None
    allow_free_text: bool = True
    allow_numeric_input: bool = False

    def __post_init__(self) -> None:
        if not self.options and self.suggested_options:
            self.options = self.suggested_options
        elif not self.suggested_options and self.options:
            self.suggested_options = self.options
        if not self.question and self.questions:
            self.question = self.questions[0]
        elif not self.questions and self.question:
            self.questions = [self.question]
        if not self.evidence and self.issue_explanation:
            self.evidence = self.issue_explanation
        elif not self.issue_explanation and self.evidence:
            self.issue_explanation = self.evidence
        if not self.affected_constraints and self.affected_requirements:
            self.affected_constraints = self.affected_requirements
        elif not self.affected_requirements and self.affected_constraints:
            self.affected_requirements = self.affected_constraints

    def to_dict(self) -> Dict[str, Any]:
        d = to_jsonable(asdict(self))
        d["question"] = self.question or (self.questions[0] if self.questions else self.issue_explanation)
        d["evidence"] = self.evidence or self.issue_explanation
        d["options"] = [o.to_dict() for o in (self.options or self.suggested_options)]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClarificationRequest:
        raw_opts = data.get("options") or data.get("suggested_options") or []
        parsed_opts = [
            ClarificationOption(
                option_id=o.get("option_id", ""),
                title=o.get("title") or o.get("label", ""),
                label=o.get("label") or o.get("title", ""),
                description=o.get("description", ""),
                proposed_changes=o.get("proposed_changes", {}),
                numeric_changes=o.get("numeric_changes", {}),
                affected_rooms=o.get("affected_rooms", []),
                feasibility_type=o.get("feasibility_type", AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE),
                is_verified_feasible=o.get("is_verified_feasible", False),
                grounded_evidence=o.get("grounded_evidence"),
                action_type=o.get("action_type", "custom"),
            )
            for o in raw_opts
        ]
        cat_str = data.get("category", "CLARIFY")
        cat = ClarificationCategory(cat_str) if cat_str in ClarificationCategory.__members__ else ClarificationCategory.CLARIFY
        return cls(
            request_id=data.get("request_id", ""),
            project_id=data.get("project_id", ""),
            state_version=int(data.get("state_version", 1)),
            category=cat,
            issue_explanation=data.get("issue_explanation", ""),
            question=data.get("question", ""),
            evidence=data.get("evidence", ""),
            is_mandatory=bool(data.get("is_mandatory", True)),
            suggested_options=parsed_opts,
            options=parsed_opts,
            default_behavior=data.get("default_behavior"),
            affected_requirements=data.get("affected_requirements", []),
            affected_constraints=data.get("affected_constraints", []),
            created_at=float(data.get("created_at", time.time())),
            paused_stage=data.get("paused_stage", "requirements"),
            status=ClarificationStatus(data.get("status", "pending")),
            questions=data.get("questions", []),
            measured_deficit_sqm=data.get("measured_deficit_sqm"),
            available_sqm=data.get("available_sqm"),
            required_sqm=data.get("required_sqm"),
            allow_free_text=bool(data.get("allow_free_text", True)),
            allow_numeric_input=bool(data.get("allow_numeric_input", False)),
        )

    def is_pending(self) -> bool:
        return self.status == ClarificationStatus.PENDING


@dataclass
class ClarificationResponse:
    """User response authorizing requirement changes or selecting an alternative."""

    request_id: str = ""
    project_id: str = ""
    response_id: str = ""
    selected_option_id: Optional[str] = None
    user_text: Optional[str] = None
    user_response_text: Optional[str] = None
    numeric_values: Dict[str, float] = field(default_factory=dict)
    numeric_overrides: Dict[str, float] = field(default_factory=dict)
    revised_requirements: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None
    status: str = "accepted"  # "accepted", "rejected"
    resulting_state_version: Optional[int] = None
    expected_state_version: Optional[int] = None
    rejection_reason: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.response_id:
            self.response_id = f"resp_{generate_id()}"
        if not self.user_text and self.user_response_text:
            self.user_text = self.user_response_text
        elif not self.user_response_text and self.user_text:
            self.user_response_text = self.user_text
        if not self.numeric_values and self.numeric_overrides:
            self.numeric_values = dict(self.numeric_overrides)
        elif not self.numeric_overrides and self.numeric_values:
            self.numeric_overrides = dict(self.numeric_values)

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


@dataclass
class RequirementChangeRecord:
    """Auditable provenance record tracking user-authorized requirement modifications."""

    change_id: str
    timestamp: float
    request_id: str
    response_id: str
    previous_state_version: int
    new_state_version: int
    original_requirement: Dict[str, Any]
    new_requirement: Dict[str, Any]
    reason: str
    feasibility_result_after: Optional[Dict[str, Any]] = None
    provenance: str = "user_authorized"  # "user_authorized", "system_default", "reverted"

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(asdict(self))


# ============================================================================
# Clarification Decision Class (Dual Interface: Object and 2-Tuple)
# ============================================================================

class ClarificationDecision:
    """Decision container supporting attribute access and tuple unpacking."""

    def __init__(
        self,
        category: ClarificationCategory,
        clarification_request: Optional[ClarificationRequest] = None,
    ):
        self.category = category
        self.clarification_request = clarification_request

    @property
    def should_pause(self) -> bool:
        return self.category != ClarificationCategory.PROCEED

    def __iter__(self):
        yield self.category
        yield self.clarification_request

    def __getitem__(self, index):
        return (self.category, self.clarification_request)[index]

    def __repr__(self) -> str:
        return f"ClarificationDecision(category={self.category.value}, should_pause={self.should_pause})"


# ============================================================================
# Clarification Decision Policy & Grounded Option Generation
# ============================================================================

class ClarificationDecisionPolicy:
    """Authoritative decision policy evaluating project state, completeness,
    and feasibility to determine whether user clarification is necessary.
    """

    @classmethod
    def evaluate(
        cls,
        project_id_or_state: Any = None,
        state_version: Optional[int] = None,
        requirements: Optional[Requirements] = None,
        completeness_result: Optional[Any] = None,
        feasibility_facts: Optional[Dict[str, Any]] = None,
        open_questions: Optional[List[str]] = None,
        *,
        project_id: Optional[str] = None,
        **kwargs: Any,
    ) -> ClarificationDecision:
        """Determine next clarification action.

        Supports both:
          evaluate(state: ProjectState)
          evaluate(project_id=..., state_version=..., ...)
        """
        # 1. Adapt from ProjectState if passed
        state_obj = project_id_or_state if (project_id_or_state and hasattr(project_id_or_state, "project_id") and hasattr(project_id_or_state, "version")) else kwargs.get("state")

        if state_obj:
            project_id = project_id or state_obj.project_id
            state_version = state_version if state_version is not None else state_obj.version
            requirements = requirements or state_obj.get_artifact("requirements")
            completeness_result = completeness_result or state_obj.get_artifact("completeness_result")
            feasibility_facts = feasibility_facts or state_obj.facts.get("feasibility_facts", state_obj.facts)
            open_questions = open_questions or list(state_obj.open_questions)
        else:
            project_id = str(project_id or project_id_or_state or "proj_unknown")
            state_version = int(state_version or 1)
            feasibility_facts = feasibility_facts or {}
            open_questions = list(open_questions or [])
            feasibility_facts = feasibility_facts or {}
            open_questions = list(open_questions or [])

        req_id = f"clarif_{generate_id()}"
        questions = list(open_questions)

        # 2. Mathematical Boundary Capacity & Deficit Pre-Check
        if requirements:
            w, l = getattr(requirements, "plot_dimensions", None) or (0.0, 0.0)
            sb = getattr(requirements, "setbacks", {}) or {}
            front = float(sb.get("front", 0.0))
            rear = float(sb.get("rear", 0.0))
            left = float(sb.get("left", 0.0))
            right = float(sb.get("right", 0.0))

            # Contradictory setbacks exceeding plot boundaries
            if (l > 0 and (front + rear >= l)) or (w > 0 and (left + right >= w)):
                explanation = (
                    f"Contradictory plot setbacks: front ({front}m) + rear ({rear}m) = {front + rear}m "
                    f"exceeds or equals plot depth {l}m."
                )
                req = ClarificationRequest(
                    request_id=req_id,
                    project_id=project_id,
                    state_version=state_version,
                    category=ClarificationCategory.REQUEST_CONSTRAINT_REVISION,
                    issue_explanation=explanation,
                    question=explanation,
                    evidence=f"Plot: {w}m x {l}m; Setbacks: Front={front}m, Rear={rear}m, Left={left}m, Right={right}m",
                    is_mandatory=True,
                    affected_requirements=["setbacks", "plot_dimensions"],
                    affected_constraints=["plot_boundary"],
                    paused_stage="requirements",
                )
                return ClarificationDecision(ClarificationCategory.REQUEST_CONSTRAINT_REVISION, req)

            # Check if total rooms is zero
            if requirements.total_rooms() == 0:
                explanation = "Room requirements are incomplete: no rooms have been specified for this floor plan."
                req = ClarificationRequest(
                    request_id=req_id,
                    project_id=project_id,
                    state_version=state_version,
                    category=ClarificationCategory.CLARIFY,
                    issue_explanation=explanation,
                    question=explanation,
                    evidence="Requirements contains 0 room requirements.",
                    is_mandatory=True,
                    affected_requirements=["room_requirements"],
                    paused_stage="requirements",
                    questions=["Please specify which rooms you require (e.g. bedrooms, living, kitchen)."],
                )
                return ClarificationDecision(ClarificationCategory.CLARIFY, req)

            # Calculate physical buildable footprint capacity
            bw = max(0.0, w - left - right)
            bl = max(0.0, l - front - rear)
            buildable_sqm = bw * bl
            target_floors = requirements.target_floors or (len(requirements.floors) if requirements.floors else 1)
            max_capacity = buildable_sqm * target_floors

            total_min_req_sqm = 0.0
            for fl in requirements.floors or []:
                for rm in fl.room_requirements:
                    total_min_req_sqm += float(rm.min_area_sqm or rm.preferred_area_sqm or rm.target_area_sqm or 0.0)

            if buildable_sqm > 0 and total_min_req_sqm > max_capacity:
                deficit = total_min_req_sqm - max_capacity
                feasibility_facts = {
                    "feasible": False,
                    "deficits": [
                        {
                            "floor": 1,
                            "deficit_sqm": round(deficit, 2),
                            "available_sqm": round(max_capacity, 2),
                            "required_sqm": round(total_min_req_sqm, 2),
                        }
                    ],
                    "buildable_area_sqm": round(max_capacity, 2),
                }

        # 3. Check Infeasibility & Physical Deficits (Category: REQUEST_CONSTRAINT_REVISION)
        if feasibility_facts.get("feasible") is False or feasibility_facts.get("deficits"):
            deficits = feasibility_facts.get("deficits", [])
            total_deficit = sum(float(d.get("deficit_sqm", 0.0)) for d in deficits) if deficits else 0.0
            available_buildable = float(feasibility_facts.get("buildable_area_sqm", 0.0))
            required_sqm = None
            if deficits:
                available_buildable = float(deficits[0].get("available_sqm", available_buildable))
                required_sqm = float(deficits[0].get("required_sqm", available_buildable + total_deficit))

            options = cls._generate_grounded_infeasibility_options(
                requirements=requirements,
                deficit_sqm=total_deficit,
                available_sqm=available_buildable,
                deficits=deficits,
            )

            explanation = (
                f"The requested room program is physically infeasible: Total minimum required area "
                f"exceeds available buildable footprint by {total_deficit:.1f} m². "
                f"Please choose an authorized adjustment to proceed."
            )

            req = ClarificationRequest(
                request_id=req_id,
                project_id=project_id,
                state_version=state_version,
                category=ClarificationCategory.REQUEST_CONSTRAINT_REVISION,
                issue_explanation=explanation,
                question=explanation,
                evidence=f"Measured required: {required_sqm:.1f} m²; Available buildable: {available_buildable:.1f} m²; Deficit: {total_deficit:.1f} m²",
                is_mandatory=True,
                suggested_options=options,
                options=options,
                default_behavior="Decline revision and terminate as infeasible",
                affected_requirements=["room_areas", "plot_boundary", "floor_count"],
                affected_constraints=["physical_feasibility", "plot_boundary"],
                paused_stage="feasibility_check",
                questions=[explanation],
                measured_deficit_sqm=round(total_deficit, 2),
                available_sqm=round(available_buildable, 2),
                required_sqm=round(required_sqm or (available_buildable + total_deficit), 2),
                allow_free_text=True,
                allow_numeric_input=True,
            )
            return ClarificationDecision(ClarificationCategory.REQUEST_CONSTRAINT_REVISION, req)

        # 4. Check Completeness Gate (Category: CLARIFY)
        if completeness_result and not getattr(completeness_result, "can_proceed", True):
            missing = list(getattr(completeness_result, "missing_fields", []))
            comp_questions = list(getattr(completeness_result, "clarification_questions", []))
            all_questions = list(set(questions + comp_questions))

            options = cls._generate_completeness_options(missing, requirements)
            explanation = f"Essential architectural requirements are missing: {', '.join(missing)}."

            req = ClarificationRequest(
                request_id=req_id,
                project_id=project_id,
                state_version=state_version,
                category=ClarificationCategory.CLARIFY,
                issue_explanation=explanation,
                question=all_questions[0] if all_questions else explanation,
                evidence=f"Completeness check reported missing: {', '.join(missing)}",
                is_mandatory=True,
                suggested_options=options,
                options=options,
                default_behavior="Apply standard residential defaults where permitted",
                affected_requirements=missing,
                affected_constraints=missing,
                paused_stage="requirements",
                questions=all_questions or [explanation],
            )
            return ClarificationDecision(ClarificationCategory.CLARIFY, req)

        # 5. Check for Open Questions (Category: CLARIFY)
        if questions:
            req = ClarificationRequest(
                request_id=req_id,
                project_id=project_id,
                state_version=state_version,
                category=ClarificationCategory.CLARIFY,
                issue_explanation="Unresolved requirement questions need your clarification.",
                question=questions[0],
                evidence="Ambiguous or missing requirement specifications in user brief.",
                is_mandatory=True,
                suggested_options=[],
                options=[],
                default_behavior=None,
                affected_requirements=["requirements"],
                paused_stage="requirements",
                questions=questions,
            )
            return ClarificationDecision(ClarificationCategory.CLARIFY, req)

        # 6. Requirements are complete and feasible (Category: PROCEED)
        return ClarificationDecision(ClarificationCategory.PROCEED, None)

    @classmethod
    def _generate_grounded_infeasibility_options(
        cls,
        requirements: Optional[Requirements],
        deficit_sqm: float,
        available_sqm: float,
        deficits: List[Dict[str, Any]],
    ) -> List[ClarificationOption]:
        """Generate options mathematically grounded in the actual deficit."""
        options: List[ClarificationOption] = []

        # Option A: Expand site boundary / buildable footprint
        needed_buildable = available_sqm + deficit_sqm + 5.0
        w, current_depth = getattr(requirements, "plot_dimensions", None) or (10.0, 10.0)
        bw = max(1.0, w - 3.0)  # estimate side setbacks
        new_depth = round((needed_buildable / bw) + 4.0, 1)

        options.append(
            ClarificationOption(
                option_id="expand_plot_depth",
                label="Expand Plot Depth",
                title="Expand Plot Depth",
                description=(
                    f"Increase plot length from {current_depth:.1f}m to {new_depth:.1f}m "
                    f"to provide sufficient buildable footprint ({needed_buildable:.1f} m²)."
                ),
                proposed_changes={
                    "action": "expand_plot",
                    "plot_length": new_depth,
                    "target_buildable_sqm": needed_buildable,
                },
                numeric_changes={"plot_length": new_depth},
                feasibility_type=AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE,
                is_verified_feasible=False,
                grounded_evidence=f"Calculated from deficit {deficit_sqm:.1f} m² + current {available_sqm:.1f} m²",
                action_type="expand_plot",
            )
        )

        # Option B: Distribute rooms across additional floor(s)
        current_floors = requirements.target_floors or (len(requirements.floors) if requirements and requirements.floors else 1)
        new_floors = current_floors + 1
        options.append(
            ClarificationOption(
                option_id="opt_add_floor",
                label=f"Distribute Across {new_floors} Floors",
                title=f"Distribute Across {new_floors} Floors",
                description=(
                    f"Add an upper floor to distribute rooms vertically across {new_floors} floors, "
                    f"reducing footprint pressure on Floor 1."
                ),
                proposed_changes={
                    "action": "add_floor",
                    "target_floors": new_floors,
                    "new_floor_count": new_floors,
                },
                numeric_changes={"target_floors": float(new_floors)},
                feasibility_type=AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE,
                is_verified_feasible=False,
                grounded_evidence=f"Spreads {deficit_sqm:.1f} m² program across {new_floors} floors",
                action_type="add_floor",
            )
        )

        # Option C: Reduce optional rooms or scale down room target sizes
        optional_rooms: List[str] = []
        if requirements:
            for f in requirements.floors or []:
                for r in getattr(f, "room_requirements", []) or []:
                    rtype = getattr(r, "room_type", "").lower()
                    desc = getattr(r, "description", "").lower()
                    if rtype in ("study", "office", "balcony", "guest_room", "utility", "powder_room") or "optional" in desc:
                        optional_rooms.append(rtype)

        if optional_rooms:
            opt_room = optional_rooms[0]
            options.append(
                ClarificationOption(
                    option_id=f"remove_optional_{opt_room}",
                    label=f"Remove Optional {opt_room.title()}",
                    title=f"Remove Optional {opt_room.title()}",
                    description=(
                        f"Remove the {opt_room.title()} from requirements to fit the essential rooms "
                        f"within the current site boundaries."
                    ),
                    proposed_changes={
                        "action": "remove_room",
                        "room_type": opt_room,
                    },
                    affected_rooms=[opt_room],
                    feasibility_type=AlternativeFeasibilityType.UNVERIFIED_HYPOTHETICAL,
                    is_verified_feasible=False,
                    grounded_evidence=f"Identified {opt_room} as non-mandatory secondary space",
                    action_type="remove_optional_room",
                )
            )

        # Option D: Decline revision and terminate
        options.append(
            ClarificationOption(
                option_id="opt_terminate_infeasible",
                label="Decline Revision (Terminate Workflow)",
                title="Decline Revision (Terminate Workflow)",
                description="Keep current constraints unchanged and conclude workflow with truthful infeasibility status.",
                proposed_changes={"action": "terminate"},
                feasibility_type=AlternativeFeasibilityType.VERIFIED_FEASIBLE,
                is_verified_feasible=True,
                grounded_evidence="Maintains strict user constraints without fabrication",
                action_type="cancel",
            )
        )

        return options

    @classmethod
    def _generate_completeness_options(
        cls,
        missing_fields: List[str],
        requirements: Optional[Requirements],
    ) -> List[ClarificationOption]:
        """Generate options for missing fields."""
        options: List[ClarificationOption] = []
        if "plot_boundary" in missing_fields or "plot_shape" in missing_fields:
            options.append(
                ClarificationOption(
                    option_id="opt_default_rectangular_plot",
                    label="Use Standard Rectangular Plot (15m × 20m)",
                    title="Use Standard Rectangular Plot (15m × 20m)",
                    description="Adopt standard 300 m² rectangular plot with standard 1.5m setbacks.",
                    proposed_changes={
                        "action": "set_plot_shape",
                        "plot_length": 20.0,
                        "plot_width": 15.0,
                    },
                    numeric_changes={"plot_length": 20.0, "plot_width": 15.0},
                    feasibility_type=AlternativeFeasibilityType.SUGGESTED_ALTERNATIVE,
                    is_verified_feasible=True,
                    action_type="custom",
                )
            )
        return options


# ============================================================================
# Response Validation & Atomic Requirement Mutation
# ============================================================================

class ClarificationResponseValidator:
    """Strict validator for incoming user clarification responses."""

    @classmethod
    def validate_and_apply(
        cls,
        *args: Any,
        **kwargs: Any,
    ) -> Tuple[bool, str, Any, Optional[Any]]:
        """Validate response and compute updated Requirements atomically.

        Supports two call signatures:
        1. validate_and_apply(state: ProjectState, request_id: str, selected_option_id=..., ...)
        2. validate_and_apply(request: ClarificationRequest, response: ClarificationResponse, current_state_version: int, current_requirements: Optional[Requirements])
        """
        # Signature 1: called with ProjectState
        if "state" in kwargs or (len(args) > 0 and hasattr(args[0], "project_id") and hasattr(args[0], "pending_clarification")):
            state = kwargs.get("state") if "state" in kwargs else args[0]
            request_id = kwargs.get("request_id") if "request_id" in kwargs else (args[1] if len(args) > 1 else "")
            selected_option_id = kwargs.get("selected_option_id")
            user_response_text = kwargs.get("user_response_text")
            numeric_overrides = kwargs.get("numeric_overrides")
            expected_state_version = kwargs.get("expected_state_version")

            return cls._apply_to_project_state(
                state=state,
                request_id=request_id,
                selected_option_id=selected_option_id,
                user_response_text=user_response_text,
                numeric_overrides=numeric_overrides,
                expected_state_version=expected_state_version,
            )

        # Signature 2: called with (request, response, current_state_version, current_requirements)
        request = kwargs.get("request") if "request" in kwargs else args[0]
        response = kwargs.get("response") if "response" in kwargs else args[1]
        current_state_version = kwargs.get("current_state_version") if "current_state_version" in kwargs else args[2]
        current_requirements = kwargs.get("current_requirements") if "current_requirements" in kwargs else args[3]

        return cls._apply_lower_level(
            request=request,
            response=response,
            current_state_version=current_state_version,
            current_requirements=current_requirements,
        )

    @classmethod
    def _apply_to_project_state(
        cls,
        state: Any,
        request_id: str,
        selected_option_id: Optional[str] = None,
        user_response_text: Optional[str] = None,
        numeric_overrides: Optional[Dict[str, float]] = None,
        expected_state_version: Optional[int] = None,
    ) -> Tuple[bool, str, Optional[ClarificationResponse]]:
        """Validate and atomically apply changes to a ProjectState."""
        from app.agentic.state import RunStatus

        pending: Optional[ClarificationRequest] = state.pending_clarification
        if not pending:
            return False, f"No pending clarification request for project '{state.project_id}'.", None

        # Request ID check
        if pending.request_id != request_id:
            return (
                False,
                f"Clarification request ID mismatch: pending '{pending.request_id}' != submitted '{request_id}'.",
                None,
            )

        # Stale state version check
        if expected_state_version is not None and expected_state_version != state.version:
            return (
                False,
                f"Stale response rejected: expected state version {expected_state_version} but current is {state.version}.",
                None,
            )

        # Validate option if specified
        matched_option: Optional[ClarificationOption] = None
        available_options = pending.options or pending.suggested_options
        if selected_option_id:
            for opt in available_options:
                if opt.option_id == selected_option_id:
                    matched_option = opt
                    break
            if not matched_option:
                return (
                    False,
                    f"Invalid selected_option_id '{selected_option_id}'. Options: {[o.option_id for o in available_options]}",
                    None,
                )

        # Handle user termination selection
        if selected_option_id == "opt_terminate_infeasible":
            pending.status = ClarificationStatus.ANSWERED
            state.clarification_history.append(pending)
            state.pending_clarification = None
            state.status = RunStatus.INFEASIBLE
            state.status_reason = "User declined constraint revision; design confirmed infeasible under original inputs."
            clarif_resp = ClarificationResponse(
                response_id=f"resp_{generate_id()}",
                request_id=request_id,
                project_id=state.project_id,
                selected_option_id=selected_option_id,
                status="accepted",
                resulting_state_version=state.version,
            )
            return True, "User authorized termination under original infeasible constraints.", clarif_resp

        # Atomically mutate cloned requirements
        current_req = state.get_artifact("requirements")
        req_clone: Requirements = copy.deepcopy(current_req) if current_req else Requirements()

        reason_parts: List[str] = []

        if matched_option:
            reason_parts.append(f"Selected option '{matched_option.title or matched_option.label}'")
            # Apply option numeric changes
            for k, v in matched_option.numeric_changes.items():
                if k == "plot_length":
                    w = req_clone.plot_dimensions[0] if req_clone.plot_dimensions else 10.0
                    req_clone.plot_dimensions = (w, float(v))
                    reason_parts.append(f"Updated plot length to {v}m")
                elif k == "plot_width":
                    l = req_clone.plot_dimensions[1] if req_clone.plot_dimensions else 10.0
                    req_clone.plot_dimensions = (float(v), l)
                    reason_parts.append(f"Updated plot width to {v}m")
                elif k == "target_floors":
                    req_clone.target_floors = int(v)
                    reason_parts.append(f"Set target floors to {int(v)}")

            # Apply option action type
            if matched_option.action_type == "add_floor" or "target_floors" in matched_option.proposed_changes:
                new_fl_count = int(matched_option.proposed_changes.get("target_floors", req_clone.target_floors or 2))
                req_clone.target_floors = new_fl_count
                while len(req_clone.floors) < new_fl_count:
                    next_fl_num = len(req_clone.floors) + 1
                    req_clone.floors.append(
                        FloorRequirement(floor_number=next_fl_num, floor_name=f"Floor {next_fl_num}", room_requirements=[])
                    )
                reason_parts.append(f"Expanded floor program to {new_fl_count} floors")

            elif matched_option.action_type == "remove_optional_room" or matched_option.affected_rooms:
                for rm_to_rm in matched_option.affected_rooms:
                    for fl in req_clone.floors or []:
                        fl.room_requirements = [
                            r for r in fl.room_requirements
                            if r.room_type.lower() != rm_to_rm.lower()
                        ]
                    reason_parts.append(f"Removed optional room '{rm_to_rm}'")

        # Direct user numeric overrides
        if numeric_overrides:
            for k, v in numeric_overrides.items():
                if k == "plot_length":
                    w = req_clone.plot_dimensions[0] if req_clone.plot_dimensions else 10.0
                    req_clone.plot_dimensions = (w, float(v))
                    reason_parts.append(f"User overrode plot length to {v}m")
                elif k == "plot_width":
                    l = req_clone.plot_dimensions[1] if req_clone.plot_dimensions else 10.0
                    req_clone.plot_dimensions = (float(v), l)
                    reason_parts.append(f"User overrode plot width to {v}m")
                elif k == "target_floors":
                    req_clone.target_floors = int(v)
                    reason_parts.append(f"User overrode target floors to {int(v)}")

        if user_response_text:
            reason_parts.append(f"User text: {user_response_text}")

        # Update ProjectState artifacts and lifecycle
        old_version = state.version
        state.set_artifact("requirements", req_clone)
        state.status = RunStatus.RESUMABLE
        state.status_reason = "Clarification response accepted; ready to resume workflow."

        pending.status = ClarificationStatus.ANSWERED
        state.clarification_history.append(pending)
        state.pending_clarification = None

        # Downstream invalidation: wipe planning_spec, allocation_set, architectural_design_set, floor_plan_set
        state.invalidate_downstream("requirements")

        change_record = RequirementChangeRecord(
            change_id=f"change_{generate_id()}",
            timestamp=time.time(),
            request_id=request_id,
            response_id=f"resp_{generate_id()}",
            previous_state_version=old_version,
            new_state_version=state.version,
            original_requirement=to_jsonable(asdict(current_req)) if current_req else {},
            new_requirement=to_jsonable(asdict(req_clone)) if req_clone else {},
            reason="; ".join(reason_parts) or "User clarification applied.",
            provenance="user_authorized",
        )
        state.requirement_changes.append(change_record)

        clarif_resp = ClarificationResponse(
            response_id=change_record.response_id,
            request_id=request_id,
            project_id=state.project_id,
            selected_option_id=selected_option_id,
            user_text=user_response_text,
            numeric_values=numeric_overrides or {},
            status="accepted",
            resulting_state_version=state.version,
        )

        return True, "Clarification response accepted and requirements updated.", clarif_resp

    @classmethod
    def _apply_lower_level(
        cls,
        request: ClarificationRequest,
        response: ClarificationResponse,
        current_state_version: int,
        current_requirements: Optional[Requirements],
    ) -> Tuple[bool, str, Optional[Requirements], Optional[RequirementChangeRecord]]:
        """Validate response and compute updated Requirements atomically (lower-level signature)."""
        exp_ver = response.expected_state_version if response.expected_state_version is not None else response.resulting_state_version
        if exp_ver is not None and exp_ver != current_state_version:
            return (
                False,
                f"Stale response rejected: Response referenced state_version {exp_ver} "
                f"but current state_version is {current_state_version}.",
                None,
                None,
            )

        if response.request_id != request.request_id:
            return (
                False,
                f"Request ID mismatch: Response referenced '{response.request_id}' "
                f"but pending request is '{request.request_id}'.",
                None,
                None,
            )

        if not request.is_pending():
            return (
                False,
                f"Clarification request '{request.request_id}' is no longer pending (status: {request.status.value}).",
                None,
                None,
            )

        selected_opt: Optional[ClarificationOption] = None
        available_options = request.options or request.suggested_options
        if response.selected_option_id:
            for opt in available_options:
                if opt.option_id == response.selected_option_id:
                    selected_opt = opt
                    break
            if not selected_opt:
                return (
                    False,
                    f"Invalid option ID '{response.selected_option_id}'. Allowed: {[o.option_id for o in available_options]}",
                    None,
                    None,
                )

        req_clone: Optional[Requirements] = copy.deepcopy(current_requirements) if current_requirements else None
        reason = f"Selected option '{selected_opt.title or selected_opt.label}'" if selected_opt else "Clarification applied."
        orig_dict = to_jsonable(asdict(current_requirements)) if current_requirements else {}

        if selected_opt and req_clone:
            for k, v in selected_opt.numeric_changes.items():
                if k == "plot_length":
                    w = req_clone.plot_dimensions[0] if req_clone.plot_dimensions else 10.0
                    req_clone.plot_dimensions = (w, float(v))
                elif k == "plot_width":
                    l = req_clone.plot_dimensions[1] if req_clone.plot_dimensions else 10.0
                    req_clone.plot_dimensions = (float(v), l)
                elif k == "target_floors":
                    req_clone.target_floors = int(v)

        if response.numeric_values and req_clone:
            for k, v in response.numeric_values.items():
                if k == "plot_length":
                    w = req_clone.plot_dimensions[0] if req_clone.plot_dimensions else 10.0
                    req_clone.plot_dimensions = (w, float(v))
                elif k == "plot_width":
                    l = req_clone.plot_dimensions[1] if req_clone.plot_dimensions else 10.0
                    req_clone.plot_dimensions = (float(v), l)
                elif k == "target_floors":
                    req_clone.target_floors = int(v)

        change_rec = RequirementChangeRecord(
            change_id=f"change_{generate_id()}",
            timestamp=time.time(),
            request_id=request.request_id,
            response_id=response.response_id,
            previous_state_version=current_state_version,
            new_state_version=current_state_version + 1,
            original_requirement=orig_dict,
            new_requirement=to_jsonable(asdict(req_clone)) if req_clone else {},
            reason=reason,
            provenance="user_authorized",
        )

        return True, "Clarification response accepted and applied.", req_clone, change_rec
