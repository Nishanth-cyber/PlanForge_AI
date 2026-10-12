"""Architectural Agent implementation for PlanForge AI.

Transforms strategic PlanningSpec and ASAA AllocatedRegions into structured
architectural design proposals (HOW) using the Architectural LLM.
"""

from __future__ import annotations
import json
import logging
from typing import Any, Optional
from app.agents.architectural_agent.context import (
    ArchitecturalContext,
    ContextBuilder,
    FloorDesignContext,
)

logger = logging.getLogger(__name__)
from app.agents.architectural_agent.prompts import (
    ARCHITECTURAL_SYSTEM_PROMPT,
    build_floor_prompt,
)
from app.agents.architectural_agent.structured_output import (
    ArchitecturalOutputValidator,
    MalformedLLMResponseError,
)
from app.llm.client import LLMClient, MockLLMClient
from app.llm.configuration import LLMConfig
from app.llm.factory import create_llm_client
from app.llm.response_parser import LLMResponseParser
from app.models.allocation import AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.planning import PlanningSpec
from app.models.requirements import Requirements
from app.models.staircase import StaircaseIntent
from app.utils.ids import generate_id


class ArchitecturalAgent:
    """Authoritative agent for architectural room, door, and window design proposals."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[LLMConfig] = None,
    ):
        """Initialize ArchitecturalAgent.

        Args:
            llm_client: Optional LLMClient instance. If None, created from config.
            config: Optional LLMConfig. Defaults to MockLLMClient.
        """
        self.config = config or LLMConfig.from_env()
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            # If creating a MockLLMClient by default, provide the smart deterministic generator
            if self.config.provider == "mock":
                self.llm_client = MockLLMClient(
                    generator=self._deterministic_mock_generator
                )
            else:
                self.llm_client = create_llm_client(self.config)


    def design(
        self,
        planning_spec: PlanningSpec,
        allocation_set: AllocationSet,
        requirements: Optional[Requirements] = None,
        strategy: Optional[str] = None,
        alternative_index: int = 0,
    ) -> ArchitecturalDesignSet:
        """Generate architectural design proposals for all allocated floors.

        Args:
            planning_spec: PlanningSpec from Planning Agent.
            allocation_set: AllocationSet from ASAA.
            requirements: Optional structured Requirements from Requirement Agent.
            strategy: Optional architectural design strategy for diversity exploration.
            alternative_index: Zero-indexed counter of candidate alternative.

        Returns:
            ArchitecturalDesignSet containing complete architectural proposals.

        Raises:
            ArchitecturalLLMError: If LLM output fails schema validation or bounds checks.
        """
        # 1. Build immutable architectural context
        context = ContextBuilder.build(
            planning_spec=planning_spec,
            allocation_set=allocation_set,
            requirements=requirements,
            strategy=strategy,
            alternative_index=alternative_index,
        )

        design_set = ArchitecturalDesignSet(
            id=generate_id("arch_set"),
            allocation_set_id=allocation_set.id,
        )

        # 2. Process each floor independently
        for floor_ctx in context.floors:
            floor_design = self._design_floor(floor_ctx, allocation_set)
            design_set.designs.append(floor_design)

        return design_set

    def _design_floor(
        self,
        floor_ctx: FloorDesignContext,
        allocation_set: AllocationSet,
    ) -> ArchitecturalDesign:
        """Design proposals for a single floor."""
        allocation = allocation_set.get_allocation(floor_ctx.floor_number)
        alloc_id = allocation.id if allocation else None

        # Build prompt and execute LLM call
        prompt = build_floor_prompt(floor_ctx)
        fallback_invoked = False
        try:
            response_text = self.llm_client.generate(
                prompt=prompt,
                system_prompt=ARCHITECTURAL_SYSTEM_PROMPT,
            )
        except Exception as e:
            logger.warning(
                "Architectural LLM call failed (%s: %s). Activating bounded deterministic fallback.",
                type(e).__name__,
                e,
            )
            response_text = self._deterministic_mock_generator(prompt, ARCHITECTURAL_SYSTEM_PROMPT)
            fallback_invoked = True

        # Parse JSON from response
        try:
            parsed_dict = LLMResponseParser.parse_json(response_text)
        except ValueError as e:
            raise MalformedLLMResponseError(
                f"Failed to parse valid JSON from LLM response for floor {floor_ctx.floor_number}: {e}"
            ) from e

        # Validate response against schema and bounds
        validated_rooms = ArchitecturalOutputValidator.validate_and_parse(
            raw_dict=parsed_dict,
            context=floor_ctx,
        )

        # Formulate StaircaseIntent if present in context
        stair_intent = None
        if floor_ctx.staircase_intent and floor_ctx.staircase_intent.get("required"):
            floors = floor_ctx.staircase_intent.get("connects_floors", [1, 2])
            from_fl = floors[0] if floors else 1
            to_fl = floors[-1] if len(floors) > 1 else from_fl + 1
            stair_intent = StaircaseIntent(
                id=generate_id("stair_intent"),
                from_floor=from_fl,
                to_floor=to_fl,
                stair_type="straight",
                allocated_region_id=floor_ctx.staircase_region_id,
                recommended_width=1.0,
                floor_number=floor_ctx.floor_number,
                rationale="Vertical circulation core aligned with ASAA allocated zone",
            )

        strat_prefix = f"[{floor_ctx.strategy.upper()}] " if floor_ctx.strategy else ""
        design_rationale = strat_prefix + str(parsed_dict.get("design_rationale", f"Architectural proposal for Floor {floor_ctx.floor_number}"))

        # Factual runtime metadata (enables auditing real LLM vs mock)
        endpoint = (
            getattr(self.llm_client, "endpoint", None)
            or getattr(self.llm_client, "base_url", None)
            or getattr(self.config, "api_base_url", None)
        )
        client_meta = getattr(self.llm_client, "last_metadata", {})
        metadata = {
            "provider": self.config.provider,
            "model": self.config.model_name,
            "endpoint": endpoint if self.config.provider in ("huggingface", "hf", "openrouter", "or", "google", "gemini") else None,
            "status": "success",
            "output_schema_valid": True,
            "client_metadata": client_meta,
        }

        return ArchitecturalDesign(
            id=generate_id("arch_design"),
            floor_number=floor_ctx.floor_number,
            floor_name=floor_ctx.floor_name,
            rooms=validated_rooms,
            staircase_intent=stair_intent,
            allocation_id=alloc_id,
            design_rationale=design_rationale,
            metadata=metadata,
        )

    @staticmethod
    def _deterministic_mock_generator(prompt: str, system_prompt: Optional[str] = None) -> str:
        """Default deterministic mock generator that builds valid structured proposals from prompt text."""
        # Detect strategy if present
        strategy = "social_centric"
        if "Design Strategy: " in prompt:
            strat_line = prompt.split("Design Strategy: ")[1].split("\n")[0].strip().lower()
            if strat_line:
                strategy = strat_line

        # Find room payloads in prompt
        marker = "Allocated Rooms to Design ("
        if marker not in prompt:
            return "{}"

        try:
            json_start = prompt.index("[", prompt.index(marker))
            json_end = prompt.rindex("]") + 1
            room_payloads = json.loads(prompt[json_start:json_end])
        except (ValueError, json.JSONDecodeError):
            return "{}"

        room_types_present = {r["room_type"] for r in room_payloads}
        has_living = "living" in room_types_present
        has_dining = "dining" in room_types_present
        has_kitchen = "kitchen" in room_types_present

        designed_rooms = []
        for r in room_payloads:
            user_dims = r.get("user_specified_dimensions")
            if user_dims and len(user_dims) == 2:
                w, l = float(user_dims[0]), float(user_dims[1])
                area = round(w * l, 2)
            else:
                w, l = r.get("approximate_dimensions", [3.0, 4.0])
                w = max(1.0, round(float(w), 2))
                l = max(1.0, round(float(l), 2))
                area = round(float(r.get("allocated_area_sqm", w * l)), 2)

            rtype = r.get("room_type", "")
            rcat = r.get("category", "")
            user_adjs = list(r.get("user_required_adjacencies", []))
            adj_types = list(r.get("adjacent_room_types", []))
            attached_id = r.get("attached_to_room_id")

            # Strategy-dependent room shapes and dimensions (only if dimensions were not user-specified)
            intended_shape = "rectangular"
            if not user_dims:
                if strategy in ("compact_circulation", "compact"):
                    if rcat in ("social", "private") and abs(w - l) < 1.0:
                        intended_shape = "square"
                        sq_side = round(min(w, l), 2)
                        w, l = sq_side, sq_side
                        area = round(sq_side * sq_side, 2)
                elif strategy in ("privacy_centric", "open_social"):
                    intended_shape = "rectangular"


            # Propose doors based on strategy
            doors = []

            # 1. Attached ensuite / parent suite door
            if attached_id:
                doors.append({
                    "connects_to": "parent_suite",
                    "door_type": "interior",
                    "wall_orientation": "east",
                    "recommended_width": 0.8,
                    "recommended_height": 2.1,
                    "rationale": "Private ensuite attached access",
                })

            # 2. Strategy-driven connectivity
            if strategy == "open_social":
                # Open-plan flow: Living <-> Kitchen <-> Dining directly connected
                if rtype == "living":
                    doors.append({
                        "connects_to": "exterior",
                        "door_type": "entrance",
                        "wall_orientation": "south",
                        "recommended_width": 1.2,
                        "recommended_height": 2.1,
                        "rationale": "Grand main entrance into open social space",
                    })
                    if has_kitchen and "kitchen" in adj_types:
                        doors.append({
                            "connects_to": "kitchen",
                            "door_type": "interior",
                            "wall_orientation": "east",
                            "recommended_width": 1.2,
                            "recommended_height": 2.1,
                            "rationale": "Open flow link to kitchen",
                        })
                    elif has_dining:
                        doors.append({
                            "connects_to": "dining",
                            "door_type": "interior",
                            "wall_orientation": "east",
                            "recommended_width": 1.2,
                            "recommended_height": 2.1,
                            "rationale": "Open plan connection to dining",
                        })
                elif rtype == "kitchen":
                    doors.append({
                        "connects_to": "dining" if has_dining else "living",
                        "door_type": "interior",
                        "wall_orientation": "north",
                        "recommended_width": 1.0,
                        "recommended_height": 2.1,
                        "rationale": "Open kitchen dining interface",
                    })
                elif rtype == "dining":
                    doors.append({
                        "connects_to": "living",
                        "door_type": "interior",
                        "wall_orientation": "west",
                        "recommended_width": 1.0,
                        "recommended_height": 2.1,
                        "rationale": "Direct dining to living connection",
                    })
                elif rcat == "private":
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "south",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Private room corridor access",
                    })

            elif strategy == "social_centric":
                # Living <-> Dining <-> Kitchen direct flow where adjacent
                if rtype == "living":
                    if has_dining:
                        doors.append({
                            "connects_to": "dining",
                            "door_type": "interior",
                            "wall_orientation": "east",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Direct social connection to dining",
                        })
                    else:
                        doors.append({
                            "connects_to": "circulation",
                            "door_type": "interior",
                            "wall_orientation": "north",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Circulation access",
                        })
                    doors.append({
                        "connects_to": "exterior",
                        "door_type": "entrance",
                        "wall_orientation": "south",
                        "recommended_width": 1.0,
                        "recommended_height": 2.1,
                        "rationale": "Main entrance",
                    })
                elif rtype == "dining":
                    if has_kitchen and "kitchen" in adj_types:
                        doors.append({
                            "connects_to": "kitchen",
                            "door_type": "interior",
                            "wall_orientation": "north",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Direct dining to kitchen service flow",
                        })
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "west",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Circulation access",
                    })
                elif rtype == "kitchen":
                    kit_connects = "dining" if (has_dining and "dining" in adj_types) else "circulation"
                    doors.append({
                        "connects_to": kit_connects,
                        "door_type": "interior",
                        "wall_orientation": "south" if kit_connects == "dining" else "west",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Direct service link to dining" if kit_connects == "dining" else "Circulation access",
                    })
                elif rcat == "private":
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "south",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Private room corridor access",
                    })
                elif not doors:
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "south",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "General circulation access",
                    })

            elif strategy == "corridor_centric":
                # Central corridor links all spaces
                if rtype == "living":
                    doors.append({
                        "connects_to": "exterior",
                        "door_type": "entrance",
                        "wall_orientation": "south",
                        "recommended_width": 1.0,
                        "recommended_height": 2.1,
                        "rationale": "Main entrance",
                    })
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "north",
                        "recommended_width": 1.0,
                        "recommended_height": 2.1,
                        "rationale": "Living room access to central circulation corridor",
                    })
                else:
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "south" if rcat == "private" else "west",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": f"Corridor spine access for {rtype}",
                    })

            elif strategy == "compact_circulation":
                # Compact direct linkages
                if rtype == "living":
                    doors.append({
                        "connects_to": "exterior",
                        "door_type": "entrance",
                        "wall_orientation": "south",
                        "recommended_width": 1.0,
                        "recommended_height": 2.1,
                        "rationale": "Direct entrance",
                    })
                    if has_dining and "dining" in adj_types:
                        doors.append({
                            "connects_to": "dining",
                            "door_type": "interior",
                            "wall_orientation": "east",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Compact connection to dining",
                        })
                    for br in [pr for pr in room_payloads if pr.get("category") == "private"]:
                        if br["room_type"] in adj_types:
                            doors.append({
                                "connects_to": br["room_type"],
                                "door_type": "interior",
                                "wall_orientation": "north",
                                "recommended_width": 0.9,
                                "recommended_height": 2.1,
                                "rationale": f"Direct compact access to {br['room_type']}",
                            })
                            break
                    if len(doors) < 2:
                        doors.append({
                            "connects_to": "circulation",
                            "door_type": "interior",
                            "wall_orientation": "north",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Compact circulation link",
                        })
                elif rtype == "dining":
                    if has_kitchen and "kitchen" in adj_types:
                        doors.append({
                            "connects_to": "kitchen",
                            "door_type": "interior",
                            "wall_orientation": "north",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Direct service link",
                        })
                    else:
                        doors.append({
                            "connects_to": "circulation",
                            "door_type": "interior",
                            "wall_orientation": "south",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Compact access",
                        })
                elif not doors:
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "south" if rcat == "private" else "west",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Compact room access",
                    })

            else:  # privacy_centric, service_clustered, etc.
                if rtype == "living":
                    doors.append({
                        "connects_to": "exterior",
                        "door_type": "entrance",
                        "wall_orientation": "south",
                        "recommended_width": 1.0,
                        "recommended_height": 2.1,
                        "rationale": "Entrance",
                    })
                    if has_dining and "dining" in adj_types:
                        doors.append({
                            "connects_to": "dining",
                            "door_type": "interior",
                            "wall_orientation": "east",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Direct social connection to dining",
                        })
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "east",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Buffer corridor link",
                    })
                elif rtype == "dining":
                    if has_kitchen and "kitchen" in adj_types:
                        doors.append({
                            "connects_to": "kitchen",
                            "door_type": "interior",
                            "wall_orientation": "north",
                            "recommended_width": 0.9,
                            "recommended_height": 2.1,
                            "rationale": "Direct dining to kitchen service flow",
                        })
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "south",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Access door",
                    })
                elif rcat == "private":
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "north",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Private wing secluded buffer",
                    })
                elif not doors:
                    doors.append({
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "wall_orientation": "south",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": "Access door",
                    })

            # Fallback: ensure every room has at least one door
            if not doors:
                doors.append({
                    "connects_to": "circulation",
                    "door_type": "interior",
                    "wall_orientation": "south" if rcat == "private" else "north",
                    "recommended_width": 0.9,
                    "recommended_height": 2.1,
                    "rationale": f"Default circulation access for {rtype}",
                })

            # Respect explicit user required adjacencies
            for target_type in user_adjs:
                already_has = any(d.get("connects_to") == target_type for d in doors)
                if not already_has:
                    doors.append({
                        "connects_to": target_type,
                        "door_type": "interior",
                        "wall_orientation": "north",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                        "rationale": f"User required connection to {target_type}",
                    })

            # Propose windows
            windows = []
            if rcat in {"social", "private"}:
                win_orient = "north" if rcat == "social" else "east"
                windows.append({
                    "wall_orientation": win_orient,
                    "window_type": "standard",
                    "recommended_width": 1.2,
                    "recommended_height": 1.5,
                    "sill_height": 0.9,
                    "rationale": "Daylight and natural ventilation",
                })
            elif rcat == "service":
                windows.append({
                    "wall_orientation": "west",
                    "window_type": "ventilation",
                    "recommended_width": 0.6,
                    "recommended_height": 0.6,
                    "sill_height": 1.5,
                    "rationale": "Ventilation",
                })

            connected_list = [d["connects_to"] for d in doors]

            designed_rooms.append({
                "room_id": r["room_id"],
                "room_type": r["room_type"],
                "allocated_region_id": r["allocated_region_id"],
                "floor_number": r["floor_number"],
                "intended_shape": intended_shape,
                "intended_dimensions": [w, l],
                "intended_area_sqm": area,
                "doors": doors,
                "windows": windows,
                "connected_spaces": connected_list or ["circulation"],
                "design_rationale": f"{strategy} layout for {r['room_type']}",
            })

        result_payload = {
            "floor_number": room_payloads[0].get("floor_number", 1) if room_payloads else 1,
            "design_rationale": f"Architectural proposal embodying the '{strategy}' design strategy",
            "rooms": designed_rooms,
        }
        return json.dumps(result_payload, indent=2)
