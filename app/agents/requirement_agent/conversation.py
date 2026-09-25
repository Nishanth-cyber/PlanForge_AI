"""Conversational requirement assistant service for PlanForge AI.

Coordinates multi-turn requirement collection between the user and the authoritative
RequirementAgent, generating structured dynamic question cards, progress tracking,
and final confirmation summaries without inventing requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re

from app.agents.requirement_agent.agent import RequirementAgent
from app.agents.requirement_agent.completeness_gate import (
    CompletenessGate,
    CompletenessResult,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
)
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement


@dataclass
class QuestionCardData:
    """Metadata defining the dynamic question card rendered in the chat."""
    question: str
    input_type: str  # "single_choice" | "multi_choice" | "direction" | "number" | "text" | "confirmation"
    options: list[str] = field(default_factory=list)
    field_key: Optional[str] = None
    default_value: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "input_type": self.input_type,
            "options": self.options,
            "field_key": self.field_key,
            "default_value": self.default_value,
        }


@dataclass
class RequirementProgressItem:
    """Single item in the requirement progress checklist."""
    name: str
    status: str  # "completed" | "current" | "pending"
    value: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "value": self.value,
        }


@dataclass
class ChatTurnResult:
    """Consolidated outcome of an assistant chat turn."""
    message: str
    question_card: Optional[QuestionCardData] = None
    is_ready_for_generation: bool = False
    requirements_text: str = ""
    requirements_summary: Optional[dict[str, Any]] = None
    progress: list[RequirementProgressItem] = field(default_factory=list)
    remaining_count: int = 0
    project_name: str = "PlanForge Project"
    status: str = "NEEDS_CLARIFICATION"

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "question_card": self.question_card.to_dict() if self.question_card else None,
            "is_ready_for_generation": self.is_ready_for_generation,
            "requirements_text": self.requirements_text,
            "requirements_summary": self.requirements_summary,
            "progress": [p.to_dict() for p in self.progress],
            "remaining_count": self.remaining_count,
            "project_name": self.project_name,
            "status": self.status,
        }


def format_canonical_brief(reqs: Requirements, project_name: str = "") -> str:
    """Generate canonical multi-floor brief text from Requirements."""
    lines = []
    pname = project_name or reqs.project_name or "Residential Project"
    lines.append(f"{pname}")

    if reqs.plot_shape:
        coords_str = ", ".join(f"({round(float(x), 2)}, {round(float(y), 2)})" for x, y in reqs.plot_shape)
        lines.append(f"Plot polygon: {coords_str}")
        if reqs.plot_area_sqm:
            lines.append(f"Plot area: {round(reqs.plot_area_sqm, 2)} sqm")
    elif reqs.plot_dimensions:
        w, d = reqs.plot_dimensions
        lines.append(f"Plot dimensions: {round(w, 2)}m by {round(d, 2)}m")
    elif reqs.plot_area_sqm:
        lines.append(f"Plot area: {round(reqs.plot_area_sqm, 2)} sqm")

    if reqs.orientation:
        lines.append(f"Orientation: {reqs.orientation.capitalize()}")
    if reqs.entrance_facing:
        lines.append(f"Entrance: {reqs.entrance_facing.capitalize()}")

    if reqs.setbacks:
        sb_parts = [f"{k} setback: {v}m" for k, v in reqs.setbacks.items()]
        lines.append(", ".join(sb_parts))

    if reqs.target_floors is not None:
        lines.append(f"Target floors: {reqs.target_floors}")

    tf = reqs.target_floors or (len(reqs.floors) if reqs.floors else 0)
    if tf > 0:
        for fn in range(1, tf + 1):
            fl = reqs.get_floor(fn)
            fname = f"Floor {fn}" if fn > 1 else "Floor 1 (Ground Floor)"
            lines.append(f"\n{fname}:")
            if fl and fl.room_requirements:
                for r in fl.room_requirements:
                    cnt = r.min_count or 1
                    r_name = r.room_type.replace("_", " ").title()
                    area_part = ""
                    if r.preferred_area_sqm:
                        area_part = f" of {round(r.preferred_area_sqm, 1)} sq m"
                    lines.append(f"- {cnt} {r_name}{area_part}")
            else:
                lines.append("- Rooms not yet specified")

    return "\n".join(lines).strip()


class ConversationalRequirementAssistant:
    """Authoritative multi-turn conversational coordinator for floor-plan requirements."""

    def __init__(self, requirement_agent: Optional[RequirementAgent] = None) -> None:
        self.requirement_agent = requirement_agent or RequirementAgent()

    def handle_turn(
        self,
        message: str,
        existing_brief: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> ChatTurnResult:
        """Process a single conversational user message and return next step guidance."""
        clean_msg = message.strip()
        pname = project_name or "PlanForge Residential Project"

        # Check for initial greeting/empty prompt
        if not clean_msg and not existing_brief:
            return self._initial_greeting(pname)

        # Detect edit request
        if clean_msg.lower() in ["edit requirements", "✏ edit requirements", "edit", "modify"]:
            return self._handle_edit_request(existing_brief or "", pname)

        # 1. Parse or update requirements using the authoritative agent
        if existing_brief:
            # Parse existing requirements first
            base_res = self.requirement_agent.process(existing_brief, project_name=pname)
            # Apply user message update
            res = self.requirement_agent.update(base_res.requirements, clean_msg)
        else:
            res = self.requirement_agent.process(clean_msg, project_name=pname)

        reqs = res.requirements
        comp = res.completeness
        val = res.validation

        # 2. Build progress checklist
        progress, remaining_count = self._build_progress(reqs, comp)

        # 3. Determine next question / card
        card, reply_msg = self._determine_next_step(clean_msg, reqs, comp, val, pname)

        # 4. Canonical brief
        canonical_brief = format_canonical_brief(reqs, pname)

        # 5. Check readiness
        is_ready = comp.can_proceed and val.is_valid and (card is not None and card.input_type == "confirmation")

        return ChatTurnResult(
            message=reply_msg,
            question_card=card,
            is_ready_for_generation=is_ready,
            requirements_text=canonical_brief,
            requirements_summary=self._build_summary_dict(reqs),
            progress=progress,
            remaining_count=remaining_count,
            project_name=pname,
            status=res.status,
        )

    def _initial_greeting(self, project_name: str) -> ChatTurnResult:
        """Greeting state when conversation starts."""
        progress = [
            RequirementProgressItem("Project type", "current"),
            RequirementProgressItem("Plot dimensions", "pending"),
            RequirementProgressItem("Floors", "pending"),
            RequirementProgressItem("Entrance orientation", "pending"),
            RequirementProgressItem("Floor 1 rooms", "pending"),
        ]

        card = QuestionCardData(
            question="What type of residential project would you like to design?",
            input_type="single_choice",
            options=[
                "🏠 Single-Floor Bungalow",
                "🏘 Two-Floor Duplex Residence",
                "🏢 Three-Floor Townhouse",
                "📐 Custom Dimensions & Program",
            ],
            field_key="project_type",
        )

        return ChatTurnResult(
            message=(
                "Hello! I am **PlanForge AI**, your conversational architectural assistant.\n\n"
                "Tell me about your building requirements in plain language, or choose a project type below to get started."
            ),
            question_card=card,
            is_ready_for_generation=False,
            progress=progress,
            remaining_count=5,
            project_name=project_name,
            status="INITIAL",
        )

    def _handle_edit_request(self, existing_brief: str, project_name: str) -> ChatTurnResult:
        """Handle request to edit requirements."""
        res = self.requirement_agent.process(existing_brief, project_name=project_name)
        progress, remaining_count = self._build_progress(res.requirements, res.completeness)

        card = QuestionCardData(
            question="What would you like to modify?",
            input_type="single_choice",
            options=[
                "Change Plot Dimensions",
                "Change Number of Floors",
                "Change Entrance Direction",
                "Edit Floor 1 Rooms",
                "Edit Floor 2 Rooms",
                "Looks Good, Generate Floor Plan",
            ],
            field_key="edit_selection",
        )

        return ChatTurnResult(
            message=(
                "What would you like to change? You can select a section below, or simply type your changes "
                "(e.g., *'Change plot size to 50ft x 60ft'* or *'Add a study room on Floor 1'*)."
            ),
            question_card=card,
            is_ready_for_generation=False,
            requirements_text=format_canonical_brief(res.requirements, project_name),
            requirements_summary=self._build_summary_dict(res.requirements),
            progress=progress,
            remaining_count=remaining_count,
            project_name=project_name,
            status="EDITING",
        )

    def _build_progress(
        self, reqs: Requirements, comp: CompletenessResult
    ) -> Tuple[list[RequirementProgressItem], int]:
        """Construct the compact requirement progress checklist."""
        items: list[RequirementProgressItem] = []

        # 1. Project type
        items.append(RequirementProgressItem("Project type", "completed", "Residential"))

        # 2. Plot dimensions
        if reqs.plot_shape:
            poly_desc = f"{len(reqs.plot_shape)}-point irregular"
            if reqs.plot_area_sqm:
                poly_desc += f" ({round(reqs.plot_area_sqm, 1)} m²)"
            items.append(RequirementProgressItem("Plot dimensions", "completed", poly_desc))
        elif reqs.plot_dimensions:
            w, d = reqs.plot_dimensions
            val_str = f"{round(w, 1)}m × {round(d, 1)}m"
            items.append(RequirementProgressItem("Plot dimensions", "completed", val_str))
        elif reqs.plot_area_sqm:
            items.append(RequirementProgressItem("Plot dimensions", "completed", f"{round(reqs.plot_area_sqm, 1)} m²"))
        else:
            items.append(RequirementProgressItem("Plot dimensions", "pending"))

        # 3. Floors
        if reqs.target_floors:
            items.append(RequirementProgressItem("Floors", "completed", f"{reqs.target_floors} Floor{'s' if reqs.target_floors > 1 else ''}"))
        else:
            items.append(RequirementProgressItem("Floors", "pending"))

        # 4. Entrance Orientation
        if reqs.entrance_facing or reqs.orientation:
            ent = (reqs.entrance_facing or reqs.orientation or "").capitalize()
            items.append(RequirementProgressItem("Entrance orientation", "completed", ent))
        else:
            items.append(RequirementProgressItem("Entrance orientation", "pending"))

        # 5. Floor 1 rooms
        f1 = reqs.get_floor(1)
        if f1 and f1.room_requirements:
            r_count = f1.total_rooms()
            items.append(RequirementProgressItem("Floor 1 rooms", "completed", f"{r_count} room{'s' if r_count > 1 else ''}"))
        else:
            items.append(RequirementProgressItem("Floor 1 rooms", "pending"))

        # 6. Upper Floors (if target_floors >= 2)
        tf = reqs.target_floors or (len(reqs.floors) if reqs.floors else 1)
        if tf >= 2:
            f2 = reqs.get_floor(2)
            if f2 and f2.room_requirements:
                r_count = f2.total_rooms()
                items.append(RequirementProgressItem("Floor 2 rooms", "completed", f"{r_count} room{'s' if r_count > 1 else ''}"))
            else:
                items.append(RequirementProgressItem("Floor 2 rooms", "pending"))

        if tf >= 3:
            f3 = reqs.get_floor(3)
            if f3 and f3.room_requirements:
                r_count = f3.total_rooms()
                items.append(RequirementProgressItem("Floor 3 rooms", "completed", f"{r_count} room{'s' if r_count > 1 else ''}"))
            else:
                items.append(RequirementProgressItem("Floor 3 rooms", "pending"))

        # 7. Staircase (for multi-floor)
        if tf >= 2:
            stair_mentioned = "stair" in reqs.raw_input.lower()
            if stair_mentioned:
                items.append(RequirementProgressItem("Staircase", "completed", "Configured"))
            else:
                items.append(RequirementProgressItem("Staircase", "pending"))

        # Determine remaining
        remaining = sum(1 for it in items if it.status == "pending")

        # Mark first pending item as 'current'
        found_current = False
        for it in items:
            if it.status == "pending" and not found_current:
                it.status = "current"
                found_current = True

        return items, remaining

    def _determine_next_step(
        self,
        last_user_msg: str,
        reqs: Requirements,
        comp: CompletenessResult,
        val: Any,
        project_name: str,
    ) -> Tuple[Optional[QuestionCardData], str]:
        """Determine what question card and conversational reply to present next."""

        # Priority 1: Plot dimensions missing
        has_plot = bool(reqs.plot_dimensions or reqs.plot_area_sqm or (reqs.plot_shape and len(reqs.plot_shape) >= 3))
        if not has_plot and comp.missing_fields and "plot_dimensions" in comp.missing_fields:
            reply = "What are the dimensions or total area of your plot?"
            card = QuestionCardData(
                question="Choose standard plot dimensions or enter custom size:",
                input_type="single_choice",
                options=[
                    "30ft x 40ft (1,200 sq ft)",
                    "40ft x 50ft (2,000 sq ft)",
                    "50ft x 60ft (3,000 sq ft)",
                    "10m x 15m (150 m²)",
                    "Custom Irregular Plot",
                ],
                field_key="plot_dimensions",
            )
            return card, reply

        # Priority 2: Target floors missing
        if comp.missing_fields and "target_floors" in comp.missing_fields:
            reply = "How many floors do you need for this project?"
            if reqs.plot_shape and any(k in last_user_msg.lower() for k in ["irregular", "polygon", "boundary"]):
                reply = "Got it. I've saved your custom plot boundary. Now let's define the number of floors."
            card = QuestionCardData(
                question="Select number of floors:",
                input_type="single_choice",
                options=[
                    "1 Floor (Single Storey)",
                    "2 Floors (Two Storey / Duplex)",
                    "3 Floors (Three Storey / Townhouse)",
                ],
                field_key="target_floors",
            )
            return card, reply

        # Priority 3: Entrance orientation missing (if not provided)
        if reqs.entrance_facing is None and reqs.orientation is None:
            reply = "Which direction should the main entrance face? This helps optimize solar gain and room placement."
            card = QuestionCardData(
                question="Select entrance facing direction:",
                input_type="direction",
                options=["North", "South", "East", "West"],
                field_key="entrance_facing",
            )
            return card, reply

        # Priority 4: Floor 1 rooms missing
        f1 = reqs.get_floor(1)
        if not f1 or not f1.room_requirements:
            reply = "What rooms do you need on **Floor 1 (Ground Floor)**?"
            card = QuestionCardData(
                question="Select rooms for Floor 1:",
                input_type="multi_choice",
                options=[
                    "Living Room",
                    "Kitchen",
                    "Dining Room",
                    "Master Bedroom",
                    "Bedroom",
                    "Bathroom",
                    "Study Room",
                    "Pooja Room",
                    "Porch",
                ],
                field_key="floor_1_rooms",
            )
            return card, reply

        # Priority 5: Floor 2 rooms missing (if target_floors >= 2)
        tf = reqs.target_floors or (len(reqs.floors) if reqs.floors else 1)
        if tf >= 2:
            f2 = reqs.get_floor(2)
            if not f2 or not f2.room_requirements:
                reply = "Great! Floor 1 is configured. Now, what rooms would you like on **Floor 2**?"
                card = QuestionCardData(
                    question="Select rooms for Floor 2:",
                    input_type="multi_choice",
                    options=[
                        "Master Bedroom",
                        "Bedroom",
                        "Bathroom",
                        "Study Room",
                        "Balcony",
                        "Family Lounge",
                        "Terrace",
                    ],
                    field_key="floor_2_rooms",
                )
                return card, reply

        # Priority 6: Floor 3 rooms missing (if target_floors >= 3)
        if tf >= 3:
            f3 = reqs.get_floor(3)
            if not f3 or not f3.room_requirements:
                reply = "Floor 1 and 2 are recorded. What rooms would you like on **Floor 3**?"
                card = QuestionCardData(
                    question="Select rooms for Floor 3:",
                    input_type="multi_choice",
                    options=[
                        "Bedroom",
                        "Bathroom",
                        "Gym / Fitness",
                        "Media Room",
                        "Open Terrace",
                        "Storage",
                    ],
                    field_key="floor_3_rooms",
                )
                return card, reply

        # Priority 7: Staircase location (for multi-floor, if not explicitly stated)
        if tf >= 2 and "stair" not in reqs.raw_input.lower():
            reply = "Where would you like the staircase located?"
            card = QuestionCardData(
                question="Choose preferred staircase placement:",
                input_type="single_choice",
                options=[
                    "Inside (Living Area)",
                    "Near Entrance",
                    "Central Core",
                    "Rear of House",
                    "External Staircase",
                ],
                field_key="staircase_location",
            )
            return card, reply

        # Priority 8: All requirements complete! Show final summary and confirmation card.
        summary_text = self._format_summary_markdown(reqs)
        reply = (
            f"### Plan Requirements Summary\n\n"
            f"{summary_text}\n\n"
            f"Everything looks complete and verified. Shall I generate the floor plan?"
        )
        card = QuestionCardData(
            question="Ready to generate?",
            input_type="confirmation",
            options=[
                "Generate Floor Plan",
                "Edit Requirements",
            ],
            field_key="confirmation",
        )
        return card, reply

    def _format_summary_markdown(self, reqs: Requirements) -> str:
        """Format clean Markdown summary of requirements."""
        lines = []
        if reqs.plot_dimensions:
            w, d = reqs.plot_dimensions
            w_ft = round(w * 3.28084, 1)
            d_ft = round(d * 3.28084, 1)
            area_m2 = round(w * d, 1)
            lines.append(f"• **Plot**: {round(w, 1)}m × {round(d, 1)}m ({w_ft}ft × {d_ft}ft, ~{area_m2} m²)")
        elif reqs.plot_area_sqm:
            lines.append(f"• **Plot Area**: ~{round(reqs.plot_area_sqm, 1)} m²")

        tf = reqs.target_floors or len(reqs.floors) or 1
        lines.append(f"• **Floors**: {tf}")

        ent = reqs.entrance_facing or reqs.orientation or "North"
        lines.append(f"• **Entrance Facing**: {ent.capitalize()}")

        for fn in range(1, tf + 1):
            fl = reqs.get_floor(fn)
            if fl and fl.room_requirements:
                room_strs = []
                for r in fl.room_requirements:
                    cnt = r.min_count or 1
                    rname = r.room_type.replace("_", " ").title()
                    room_strs.append(f"{cnt} {rname}" if cnt > 1 else rname)
                fname = f"Floor {fn}" if fn > 1 else "Floor 1 (Ground)"
                lines.append(f"• **{fname}**: {', '.join(room_strs)}")

        if tf >= 2:
            lines.append("• **Staircase**: Vertical Core Aligned")

        return "\n".join(lines)

    def _build_summary_dict(self, reqs: Requirements) -> dict[str, Any]:
        """Convert requirements into dictionary for frontend consumption."""
        tf = reqs.target_floors or len(reqs.floors) or 1
        floors_data = []
        for fn in range(1, tf + 1):
            fl = reqs.get_floor(fn)
            rooms = []
            if fl:
                for r in fl.room_requirements:
                    rooms.append({
                        "room_type": r.room_type,
                        "count": r.min_count,
                        "preferred_area_sqm": r.preferred_area_sqm,
                    })
            floors_data.append({"floor_number": fn, "rooms": rooms})

        return {
            "plot_dimensions": list(reqs.plot_dimensions) if reqs.plot_dimensions else None,
            "plot_area_sqm": reqs.plot_area_sqm,
            "target_floors": tf,
            "orientation": reqs.orientation,
            "entrance_facing": reqs.entrance_facing,
            "floors": floors_data,
        }
