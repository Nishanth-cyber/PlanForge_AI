"""Refinement Agent implementation for PlanForge AI.

Transforms validation feedback and existing ArchitecturalDesign proposals
into revised ArchitecturalDesign proposals (CORRECT) using the LLM.
"""

from __future__ import annotations
import copy
import json
import re
from typing import Any, Callable, Optional, Tuple

from app.agents.refinement_agent.context import RefinementContext
from app.agents.refinement_agent.output_validator import RefinementOutputValidator
from app.agents.refinement_agent.prompts import (
    REFINEMENT_SYSTEM_PROMPT,
    build_refinement_floor_prompt,
)
from app.llm.client import LLMClient, MockLLMClient
from app.llm.configuration import LLMConfig
from app.llm.factory import create_llm_client
from app.llm.response_parser import LLMResponseParser
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.refinement import RefinementChange
from app.utils.ids import generate_id


class RefinementAgent:
    """Authoritative agent for validation-driven architectural design refinement."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[LLMConfig] = None,
    ):
        """Initialize RefinementAgent.

        Args:
            llm_client: Optional LLMClient instance. If None, created from config.
            config: Optional LLMConfig. Defaults to MockLLMClient.
        """
        self.config = config or LLMConfig()
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            if self.config.provider == "mock":
                self.llm_client = MockLLMClient(
                    generator=self._deterministic_mock_refinement_generator
                )
            else:
                self.llm_client = create_llm_client(self.config)

    def refine(
        self,
        context: RefinementContext,
    ) -> Tuple[ArchitecturalDesignSet, list[RefinementChange]]:
        """Refine current architectural design based on validation feedback.

        Args:
            context: Immutable RefinementContext containing requirements, planning,
                     allocations, current design, and validation report.

        Returns:
            Tuple of (revised ArchitecturalDesignSet, list of RefinementChange).

        Raises:
            ArchitecturalLLMError: If LLM output fails validation contracts.
        """
        all_changes: list[RefinementChange] = []
        new_version = context.current_design.version + 1

        refined_set = ArchitecturalDesignSet(
            id=generate_id("arch_set_refined"),
            allocation_set_id=context.allocation_set.id,
            version=new_version,
        )

        for floor_design in context.current_design.designs:
            floor_num = floor_design.floor_number
            floor_issues = context.get_floor_issues(floor_num)
            floor_errors = [i for i in floor_issues if i.severity == "error"]

            # Minimal change principle: If this floor has zero hard errors, preserve it as-is
            if not floor_errors:
                preserved_floor = copy.deepcopy(floor_design)
                preserved_floor.version = new_version
                refined_set.designs.append(preserved_floor)
                continue

            # Floor has validation issues: invoke refinement LLM
            allocation = context.allocation_set.get_allocation(floor_num)
            if not allocation:
                # Allocation must exist
                preserved_floor = copy.deepcopy(floor_design)
                preserved_floor.version = new_version
                refined_set.designs.append(preserved_floor)
                continue

            diagnostics_text = context.format_floor_diagnostics(floor_num)
            prompt = build_refinement_floor_prompt(
                floor_design=floor_design,
                allocation=allocation,
                diagnostics_text=diagnostics_text,
                iteration=context.iteration,
                target_design_strategy=context.target_design_strategy,
            )

            # Call LLM
            response_text = self.llm_client.generate(
                prompt=prompt,
                system_prompt=REFINEMENT_SYSTEM_PROMPT,
            )

            # Parse and validate response
            raw_dict = LLMResponseParser.parse_json(response_text)
            revised_rooms, floor_changes, rationale = RefinementOutputValidator.validate_and_parse(
                raw_dict=raw_dict,
                current_floor_design=floor_design,
                allocation=allocation,
            )

            all_changes.extend(floor_changes)

            refined_floor = ArchitecturalDesign(
                id=generate_id("arch_floor_refined"),
                floor_number=floor_num,
                floor_name=floor_design.floor_name,
                rooms=revised_rooms,
                circulation_corridors=floor_design.circulation_corridors,
                staircase_intent=floor_design.staircase_intent,
                allocation_id=floor_design.allocation_id,
                design_rationale=rationale or f"Refined floor {floor_num} to resolve validation failures",
                metadata={"iteration": context.iteration},
                version=new_version,
            )
            refined_set.designs.append(refined_floor)

        return refined_set, all_changes

    @staticmethod
    def _deterministic_mock_refinement_generator(
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Deterministic mock generator for offline testing of refinement behaviors."""
        # Extract current rooms from prompt
        rooms_match = re.search(r"### CURRENT ARCHITECTURAL DESIGN.*?\n\s*(\[[\s\S]*?\])\s*\n\s*### INSTRUCTIONS", prompt)
        if not rooms_match:
            # Fallback regex if INSTRUCTIONS header is absent
            rooms_match = re.search(r"(\[\s*\{[\s\S]*\}\s*\])", prompt)
        if not rooms_match:
            # Fallback empty proposal
            return json.dumps({"rooms": [], "refinement_rationale": "No rooms found"})

        try:
            rooms = json.loads(rooms_match.group(1))
        except Exception:
            rooms = []

        # Analyze diagnostics from prompt
        is_missing_entrance = "missing_entrance_connection" in prompt
        is_isolated_room = "isolated_room" in prompt
        is_unreachable = "unreachable_from_entrance" in prompt
        is_required_adj = "required_adjacency" in prompt
        is_min_area = "min_area_violation" in prompt
        is_target_area = "target_area_undersize" in prompt
        is_win_orient = "window_orientation_mismatch" in prompt

        # Parse allocation region envelopes if present in prompt
        reg_bounds: dict[str, tuple[float, float]] = {}
        alloc_match = re.search(r"### ASSIGNED ASAA ALLOCATED REGIONS.*?\n\s*(\[[\s\S]*?\])\s*\n\s*### CURRENT", prompt)
        if alloc_match:
            try:
                for reg in json.loads(alloc_match.group(1)):
                    ad = reg.get("approximate_dimensions")
                    if ad and len(ad) >= 2:
                        reg_bounds[reg.get("id")] = (float(ad[0]), float(ad[1]))
            except Exception:
                pass

        # Perform targeted mock corrections
        for room in rooms:
            rtype = room.get("room_type", "")
            doors = room.get("doors", [])
            windows = room.get("windows", [])
            rid = room.get("id", "")

            # 1. Entrance connection correction
            if is_missing_entrance and (rtype in {"living", "foyer", "drawing"} or room == rooms[0]):
                has_entrance = any(d.get("door_type") == "entrance" for d in doors)
                if not has_entrance:
                    doors.append(
                        {
                            "wall_orientation": "south",
                            "connects_to": "exterior",
                            "door_type": "entrance",
                            "rationale": "main_entry",
                        }
                    )
                    room["design_rationale"] = "Added main exterior entrance door to resolve missing_entrance_connection"

            # 2. Isolated room / reachability correction
            if (is_isolated_room or is_unreachable) and len(doors) == 0:
                doors.append(
                    {
                        "wall_orientation": "north",
                        "connects_to": "corridor",
                        "door_type": "interior",
                        "rationale": "access",
                    }
                )
                room["design_rationale"] = "Added connecting interior door to resolve room isolation"

            # 3. Required adjacency correction
            if is_required_adj and rtype == "living":
                has_dining_door = any(d.get("connects_to") == "dining" for d in doors)
                if not has_dining_door:
                    doors.append(
                        {
                            "wall_orientation": "east",
                            "connects_to": "dining",
                            "door_type": "interior",
                            "rationale": "direct_adjacency",
                        }
                    )
                    room["design_rationale"] = "Added direct connecting door between living and dining"

            # 4. Dimension / minimum area correction (bounded by allocated envelope)
            if is_min_area:
                dims = room.get("intended_dimensions", [3.0, 3.0])
                w, l = dims[0], dims[1]
                reg_id = room.get("allocated_region_id")
                max_dims = reg_bounds.get(reg_id)
                if max_dims:
                    max_w = max(max_dims[0], max_dims[1])
                    max_l = min(max_dims[0], max_dims[1])
                    new_w = min(max_w, round(w * 1.05, 2))
                    new_l = min(max_l, round(l * 1.05, 2))
                else:
                    new_w, new_l = round(w * 1.05, 2), round(l * 1.05, 2)
                room["intended_dimensions"] = [new_w, new_l]
                room["design_rationale"] = "Adjusted room dimensions within assigned allocation bounds"

            # 5. Window orientation correction (stabilized, non-oscillating)
            if is_win_orient and windows and (f"[Room: {rid}]" in prompt or "window_orientation_mismatch" in prompt):
                for win in windows:
                    if win.get("wall_orientation") != "north":
                        win["wall_orientation"] = "north"
                        room["design_rationale"] = "Adjusted window orientation to match requested compass facade"

            room["doors"] = doors
            room["windows"] = windows

        return json.dumps(
            {
                "rooms": rooms,
                "refinement_rationale": "Applied targeted architectural corrections to resolve reported validation errors",
            },
            indent=2,
        )
