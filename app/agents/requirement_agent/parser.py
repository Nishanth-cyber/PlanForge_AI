"""Requirement Parser — extracts structured requirements from freeform text.

Implements robust extraction for:
- Plot: dimensions (w x d), area, polygon boundary, orientation, setbacks.
- Floors: target floor count, per-floor room requirements.
- Rooms: room type, quantity, isolated min/preferred/max area, attachments.
- Relationships: adjacency, separation, attached-to, circulation.
- Entrance: facing direction, preferred entrance room type.
- Staircase: required flag and location preferences.
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.agents.requirement_agent.normalizer import (
    RequirementNormalizer,
    ROOM_SYNONYMS,
    WORD_NUMBERS,
    FLOOR_LABEL_TO_NUMBER,
    CARDINAL_DIRECTIONS,
)
from app.utils.units import parse_area_sqm, parse_dimension_m


class RequirementParser:
    """Extracts architectural requirements from user text using deterministic rules."""

    def __init__(self) -> None:
        self.normalizer = RequirementNormalizer()

    def parse(self, text: str, project_name: str = "PlanForge Project") -> Requirements:
        """Parse raw text into a Requirements instance.

        Never invents unspecified fields or rooms.
        """
        raw_text = text.strip()
        reqs = Requirements(
            project_name=project_name,
            raw_input=raw_text,
        )

        # 1. Plot
        reqs.plot_dimensions = self.extract_plot_dimensions(raw_text)
        if reqs.plot_dimensions:
            w, d = reqs.plot_dimensions
            reqs.plot_area_sqm = round(w * d, 4)
        else:
            reqs.plot_area_sqm = self.extract_standalone_area(raw_text)

        reqs.plot_shape = self.extract_plot_shape(raw_text)
        if reqs.plot_shape and (reqs.plot_dimensions is None or reqs.plot_area_sqm is None):
            try:
                from shapely.geometry import Polygon
                poly = Polygon(reqs.plot_shape)
                if poly.is_valid and not poly.is_empty and poly.area > 0:
                    reqs.plot_area_sqm = round(poly.area, 4)
            except Exception:
                pass
        reqs.orientation = self.extract_orientation(raw_text)
        reqs.entrance_facing = self.extract_entrance_facing(raw_text)
        reqs.entrance_room_type = self.extract_entrance_room_type(raw_text)
        reqs.setbacks = self.extract_setbacks(raw_text)

        # 2. Target Floors
        reqs.target_floors = self.extract_target_floors(raw_text)

        # 3. Floors & Rooms
        floors = self.extract_floors(raw_text, reqs.target_floors)
        reqs.floors = floors
        reqs.floor_requirements = floors

        return reqs

    # ------------------------------------------------------------------
    # Plot Extraction
    # ------------------------------------------------------------------

    def extract_plot_dimensions(self, text: str) -> Optional[tuple[float, float]]:
        """Extract plot width and depth in metres.

        Matches:
        - 20 x 30 plot, 20 by 30 feet, 15m x 20m, 30' x 40', 30 feet by 40 feet
        """
        dim_pair = re.compile(
            r"(?:plot|site|land|ground)?(?:\s+size|\s+dimensions?)?[:\s]*"
            r"([\d]+(?:\.\d+)?)\s*"
            r"(m|meters?|metres?|ft|feet|foot|'|\u2019)?\s*"
            r"(?:x|×|\*|by)\s*"
            r"([\d]+(?:\.\d+)?)\s*"
            r"(m|meters?|metres?|ft|feet|foot|'|\u2019)?",
            re.I,
        )
        for m in dim_pair.finditer(text):
            raw_w = m.group(1)
            raw_d = m.group(3)
            unit_w = m.group(2)
            unit_d = m.group(4)

            # Suffix priority: if one unit given at the end, applies to both
            common_unit = unit_d or unit_w or ""

            def to_m(val: str, unit: str) -> float:
                token = f"{val} {unit}".strip()
                res = parse_dimension_m(token)
                return res if res is not None else float(val)

            w = to_m(raw_w, unit_w or common_unit)
            d = to_m(raw_d, unit_d or common_unit)
            if w > 0 and d > 0:
                return (round(w, 4), round(d, 4))

        return None

    def extract_standalone_area(self, text: str) -> Optional[float]:
        """Extract standalone plot area (e.g. 200 sqm, 5 marla, 1200 sq ft)."""
        pattern = re.compile(
            r"(?:plot|land|site|property)\s+(?:area|size)[:\s]*([\d]+(?:\.\d+)?\s*[a-zA-Z²]+)|"
            r"([\d]+(?:\.\d+)?\s*(?:sq\.?\s*ft|sqft|ft[²2]|sqm|sq\.?\s*m|m[²2]|marlas?|acres?|kanals?|hectares?|ha))\s+(?:plot|land|site)?",
            re.I,
        )
        m = pattern.search(text)
        if m:
            snippet = m.group(1) or m.group(2)
            val = parse_area_sqm(snippet)
            if val is not None and val > 0:
                return round(val, 4)
        return None

    def extract_plot_shape(self, text: str) -> Optional[tuple[tuple[float, float], ...]]:
        """Extract explicit boundary polygon vertices if given like:

        (0, 0), (15, 0), (15, 20), (0, 20)
        """
        # Look for parenthesised coordinate pairs: (x, y)
        coord_pat = re.compile(r"\(\s*([\d]+(?:\.\d+)?)\s*,\s*([\d]+(?:\.\d+)?)\s*\)")
        matches = coord_pat.findall(text)
        if len(matches) >= 3:
            coords = tuple((float(x), float(y)) for x, y in matches)
            return coords
        return None

    def extract_orientation(self, text: str) -> Optional[str]:
        """Extract plot orientation (e.g. north-facing)."""
        for d in CARDINAL_DIRECTIONS:
            pattern = re.compile(
                rf"\b{d}[\-\s]?facing\b|\bfacing\s+{d}\b|\b{d}\s+facing\s+(?:plot|house|site)\b|\borientation[:\s]+{d}\b",
                re.I,
            )
            if pattern.search(text):
                return d
        return None

    def extract_entrance_facing(self, text: str) -> Optional[str]:
        """Extract entrance facing direction."""
        for d in CARDINAL_DIRECTIONS:
            pattern = re.compile(
                rf"(?:main\s+)?entrance\s+(?:from|on|toward|facing)\s+(?:the\s+)?{d}\b|"
                rf"(?:main\s+)?entrance[:\s]+{d}\b|"
                rf"{d}[\-\s]facing\s+(?:main\s+)?entrance\b|"
                rf"{d}\s+entrance\b",
                re.I,
            )
            if pattern.search(text):
                return d
        return None

    def extract_entrance_room_type(self, text: str) -> Optional[str]:
        """Extract preferred room connected to main entrance (e.g. entrance to living)."""
        pattern = re.compile(
            r"(?:entrance|entry)\s+(?:leads?\s+to|opens?\s+into|to|connects?\s+to)\s+(?:the\s+)?([a-zA-Z\s]+?)(?:[,\.;]|$)",
            re.I,
        )
        m = pattern.search(text)
        if m:
            target = m.group(1).strip()
            canonical = self.normalizer.canonical_room_type(target)
            if canonical:
                return canonical
        return None

    def extract_setbacks(self, text: str) -> dict[str, float]:
        """Extract explicit setbacks."""
        setbacks: dict[str, float] = {}
        sides = ("front", "rear", "back", "left", "right", "side")
        for side in sides:
            pattern = re.compile(
                rf"{side}\s+setback[:\s]*([\d]+(?:\.\d+)?)\s*(m|meters?|ft|feet|'|\u2019)?|"
                rf"setback\s+of\s+([\d]+(?:\.\d+)?)\s*(m|meters?|ft|feet|'|\u2019)?\s+(?:on\s+the\s+)?{side}",
                re.I,
            )
            m = pattern.search(text)
            if m:
                raw_val = m.group(1) or m.group(3)
                unit = m.group(2) or m.group(4) or "m"
                val = parse_dimension_m(f"{raw_val} {unit}".strip()) or float(raw_val)
                key = "rear" if side == "back" else ("side" if side == "side" else side)
                setbacks[key] = round(val, 3)
        return setbacks

    # ------------------------------------------------------------------
    # Floors Extraction
    # ------------------------------------------------------------------

    def extract_target_floors(self, text: str) -> Optional[int]:
        """Extract explicitly stated target floor count."""
        patterns = [
            # G+1, G+2
            (r"\bG\s*\+\s*(\d+)\b", lambda m: int(m.group(1)) + 1),
            # ground + 1 upper
            (r"\bground\s*\+\s*(\d+)\s*(?:upper|floors?)?\b", lambda m: int(m.group(1)) + 1),
            # single/two/three/four/double storey or floor
            (r"\b(single|one|1)[\-\s]*(?:stor(?:ey|y)|floor)\b", lambda _: 1),
            (r"\b(two|2|double)[\-\s]*(?:stor(?:ey|y)|floor)\b", lambda _: 2),
            (r"\b(three|3|triple)[\-\s]*(?:stor(?:ey|y)|floor)\b", lambda _: 3),
            (r"\b(four|4)[\-\s]*(?:stor(?:ey|y)|floor)\b", lambda _: 4),
            # X floors / storeys / levels
            (r"\b(\d+)[\-\s]*(?:floors?|stor(?:ey|y)s?|levels?)\b", lambda m: int(m.group(1))),
            (r"\b(one|two|three|four|five)[\-\s]*(?:floors?|stor(?:ey|y)s?|levels?)\b", lambda m: WORD_NUMBERS[m.group(1).lower()]),
        ]
        for pat, fn in patterns:
            m = re.search(pat, text, re.I)
            if m:
                val = fn(m)
                if val > 0:
                    return val
        return None

    def extract_floors(self, text: str, target_floors: Optional[int]) -> list[FloorRequirement]:
        """Extract per-floor room requirements cleanly without cross-floor pollution."""
        floors: dict[int, FloorRequirement] = {}

        # 1. Split text into floor sections
        floor_sections = self._split_floor_sections(text)

        bhk_rooms = self._expand_bhk(text)

        if floor_sections:
            for fn, section_text in sorted(floor_sections.items()):
                rooms = self._extract_rooms_from_text(section_text)
                # If Floor 1 has BHK mention and no explicit rooms, add BHK rooms
                if fn == 1 and bhk_rooms and not rooms:
                    rooms = bhk_rooms
                    bhk_rooms = []
                staircase_req = self._detect_staircase(section_text, fn, target_floors)
                floors[fn] = FloorRequirement(
                    floor_number=fn,
                    floor_name=self._floor_name(fn),
                    room_requirements=rooms,
                    staircase_required=staircase_req,
                    source="user",
                )
        else:
            # Single or unified description — all rooms go to Floor 1
            rooms = self._extract_rooms_from_text(text)
            if bhk_rooms and not rooms:
                rooms = bhk_rooms
                bhk_rooms = []
            elif bhk_rooms:
                existing_types = {r.room_type for r in rooms}
                for br in bhk_rooms:
                    if br.room_type not in existing_types:
                        rooms.append(br)
            staircase_req = self._detect_staircase(text, 1, target_floors)
            floors[1] = FloorRequirement(
                floor_number=1,
                floor_name=self._floor_name(1),
                room_requirements=rooms,
                staircase_required=staircase_req,
                source="user",
            )

        # Multi-floor requirement gating safeguard:
        # If target_floors > detected floors, create empty shell FloorRequirement
        # so the Completeness Gate can detect that floor k is missing rooms.
        # NEVER invent rooms for missing floors!
        effective_floors = target_floors or (max(floors.keys()) if floors else 1)
        for fn in range(1, effective_floors + 1):
            if fn not in floors:
                floors[fn] = FloorRequirement(
                    floor_number=fn,
                    floor_name=self._floor_name(fn),
                    room_requirements=[],  # Empty! No rooms invented!
                    staircase_required=(fn > 1 or effective_floors > 1),
                    source="user",
                )

        # Ensure staircase is required on all floors when multi-floor
        if len(floors) > 1 or (target_floors and target_floors > 1):
            for fn, fr in floors.items():
                if fn > 1 or target_floors and target_floors > 1:
                    fr.staircase_required = True

        return sorted(floors.values(), key=lambda f: f.floor_number)

    def _split_floor_sections(self, text: str) -> dict[int, str]:
        """Split text into floor-labeled sections.

        Supports:
        'Ground Floor:', 'Floor 1:', '1st Floor:', 'First Floor:',
        'Floor 2:', '2nd Floor:', 'Second Floor:', 'Upper Floor:', 'Upstairs:', etc.
        Fixes regression bugs:
        - Ordinal floors ('1st floor', '2nd floor') do not crash.
        - Text before the first floor header is preserved as Floor 1 if not explicitly labeled.
        """
        # Header regex matching various floor labels at start of line or sentence
        header_pat = re.compile(
            r"(?:^|[;\n\.\b])\s*"
            r"(?:"
            r"(?:floor\s+(\d+))"  # Floor 1
            r"|(?:(\d+)(?:st|nd|rd|th)\s+floor)"  # 1st floor, 2nd floor
            r"|(?:(ground|first|second|third|fourth|fifth|lower|upper|top)\s+floor)"  # Ground floor
            r"|(?:(ground|upstairs|downstairs))"
            r")"
            r"\s*[:\-\—]?\s*",
            re.I,
        )

        matches = list(header_pat.finditer(text))
        if not matches:
            return {}

        sections: dict[int, str] = {}

        # If text precedes the first match, and contains rooms, treat as Floor 1
        first_match = matches[0]
        if first_match.start() > 0:
            pre_text = text[:first_match.start()].strip()
            if pre_text:
                sections[1] = pre_text

        for i, m in enumerate(matches):
            fn = self._match_floor_number(m)
            if fn is None:
                continue
            start_pos = m.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start_pos:end_pos].strip()

            if fn in sections:
                sections[fn] = f"{sections[fn]}\n{body}".strip()
            else:
                sections[fn] = body

        return sections

    def _match_floor_number(self, m: re.Match) -> Optional[int]:
        """Resolve regex groups into integer floor number."""
        for g in m.groups():
            if not g:
                continue
            token = g.strip().lower()
            res = self.normalizer.normalize_floor_number(token)
            if res is not None:
                return res
        return None

    def _detect_staircase(self, text: str, floor_num: int, target_floors: Optional[int]) -> bool:
        """Detect if staircase is explicitly requested or required by floor level."""
        if target_floors and target_floors > 1:
            return True
        if floor_num > 1:
            return True
        if re.search(r"\b(?:staircase|stairs?|internal\s+stairs?)\b", text, re.I):
            return True
        return False

    @staticmethod
    def _floor_name(floor_number: int) -> str:
        names = {1: "Ground Floor", 2: "First Floor", 3: "Second Floor", 4: "Third Floor"}
        return names.get(floor_number, f"Floor {floor_number}")

    # ------------------------------------------------------------------
    # Room Extraction & Area Isolation
    # ------------------------------------------------------------------

    def _extract_rooms_from_text(self, text: str) -> list[RoomRequirement]:
        """Extract rooms with isolated area, counts, attachments, and adjacencies.

        Fixes Bug 2: Multiple rooms do NOT inherit the first room's area!
        Each room's area is extracted strictly within its own sentence/line/clause.
        """
        rooms: dict[str, RoomRequirement] = {}

        # Split text into lines/clauses to prevent area bleeding across lines (do not split on decimal numbers like 3.5)
        clauses = re.split(r"[\n;]|(?<!\d)\.(?!\d)", text)


        # Build sorted list of synonym phrases (longer first)
        sorted_synonyms = sorted(ROOM_SYNONYMS.keys(), key=len, reverse=True)

        for clause in clauses:
            clause_str = clause.strip()
            if not clause_str:
                continue

            # Check for attached bathroom pattern within this clause
            attached_bath = False
            if re.search(r"\battached\s+(?:bath(?:room)?|toilet|washroom|wc)\b", clause_str, re.I):
                attached_bath = True

            occupied_spans: list[tuple[int, int]] = []

            for phrase in sorted_synonyms:
                canonical = ROOM_SYNONYMS[phrase]

                # Plural-aware pattern
                if phrase.endswith("y") and len(phrase) > 1 and phrase[-2] not in "aeiou":
                    p_esc = re.escape(phrase[:-1]) + r"(?:y|ies)"
                elif phrase.endswith(("ch", "sh", "s", "x")):
                    p_esc = re.escape(phrase) + r"(?:es|s)?"
                else:
                    p_esc = re.escape(phrase) + r"s?"

                pattern = re.compile(
                    rf"(?:(\d+|{'|'.join(WORD_NUMBERS.keys())})\s+)?"
                    rf"\b{p_esc}\b"
                    rf"(?:\s+(\d+))?",
                    re.I,
                )
                for m in pattern.finditer(clause_str):
                    m_start, m_end = m.span()
                    if any(not (m_end <= o_start or m_start >= o_end) for o_start, o_end in occupied_spans):
                        continue

                    occupied_spans.append((m_start, m_end))
                    count = self.normalizer.normalize_count(m.group(1) or m.group(2))

                    # Extract area and explicit dimensions ONLY within this specific clause/line
                    min_a, pref_a, max_a, user_d = self._extract_room_areas_from_clause(clause_str, m.start(), m.end())

                    if canonical in rooms:
                        # Increment or take max count if mentioned again
                        rooms[canonical].min_count = max(rooms[canonical].min_count, count)
                        if rooms[canonical].max_count is not None:
                            rooms[canonical].max_count = max(rooms[canonical].max_count, count)
                        if pref_a and rooms[canonical].preferred_area_sqm is None:
                            rooms[canonical].preferred_area_sqm = pref_a
                        if min_a and rooms[canonical].min_area_sqm is None:
                            rooms[canonical].min_area_sqm = min_a
                        if max_a and rooms[canonical].max_area_sqm is None:
                            rooms[canonical].max_area_sqm = max_a
                        if user_d and rooms[canonical].user_dimensions is None:
                            rooms[canonical].user_dimensions = user_d
                    else:
                        rr = RoomRequirement(
                            room_type=canonical,
                            min_count=count,
                            max_count=count,
                            min_area_sqm=min_a,
                            preferred_area_sqm=pref_a,
                            max_area_sqm=max_a,
                            user_dimensions=user_d,
                            description=clause_str,
                            source="user",
                        )
                        rooms[canonical] = rr

                    # If this room was a master bedroom and clause had attached bathroom
                    if canonical == "master_bedroom" and attached_bath:
                        rr.adjacency.append("bathroom")

        # Second pass: If attached bath was mentioned, create or update bathroom with attached_to
        if re.search(r"\battached\s+(?:bath(?:room)?|toilet|washroom)\b", text, re.I):
            # Find parent room (default master_bedroom or bedroom)
            parent = "master_bedroom" if "master_bedroom" in rooms else ("bedroom" if "bedroom" in rooms else None)
            if "bathroom" in rooms:
                rooms["bathroom"].attached_to = parent
                if parent and "bathroom" not in rooms[parent].adjacency:
                    rooms[parent].adjacency.append("bathroom")
            else:
                rooms["bathroom"] = RoomRequirement(
                    room_type="bathroom",
                    min_count=1,
                    max_count=1,
                    attached_to=parent,
                    source="user",
                )
                if parent and "bathroom" not in rooms[parent].adjacency:
                    rooms[parent].adjacency.append("bathroom")

        # Third pass: Adjacency and separation
        self._apply_relationships(text, rooms)

        return list(rooms.values())

    def _extract_room_areas_from_clause(
        self, clause: str, match_start: int, match_end: int
    ) -> tuple[Optional[float], Optional[float], Optional[float], Optional[tuple[float, float]]]:
        """Extract min, preferred, max areas and explicit dimensions strictly from within the clause."""
        user_dims: Optional[tuple[float, float]] = None

        # Check explicit dimensions: e.g. "4m x 3.5m", "4m by 3.5m", "12ft x 14ft", "12 x 14 ft"
        if not re.search(r"\b(?:plot|site|land|ground|setback)\b", clause, re.I):
            dim_pat = re.compile(
                r"([\d]+(?:\.\d+)?)\s*(m|meters?|ft|feet|'|\u2019)?\s*(?:x|by|\*)\s*([\d]+(?:\.\d+)?)\s*(m|meters?|ft|feet|'|\u2019)?",
                re.I,
            )
            dm = dim_pat.search(clause)
            if dm:
                raw_w, u_w, raw_l, u_l = dm.group(1), dm.group(2), dm.group(3), dm.group(4)
                unit_w = u_w or u_l or "m"
                unit_l = u_l or u_w or "m"
                w_val = parse_dimension_m(f"{raw_w} {unit_w}".strip())
                l_val = parse_dimension_m(f"{raw_l} {unit_l}".strip())
                if w_val and l_val and w_val > 0 and l_val > 0:
                    user_dims = (round(w_val, 2), round(l_val, 2))

        # Range check: "100 to 150 sq ft", "between 100 and 150 sq ft"
        range_pat = re.compile(
            r"(?:between\s+)?([\d]+(?:\.\d+)?)\s*(?:-|to|and)\s*([\d]+(?:\.\d+)?)\s*"
            r"(sq\.?\s*ft|sqft|ft[²2]|sqm|sq\.?\s*m|m[²2])",
            re.I,
        )
        rm = range_pat.search(clause)
        if rm:
            v1_raw = rm.group(1)
            v2_raw = rm.group(2)
            unit = rm.group(3)
            a1 = parse_area_sqm(f"{v1_raw} {unit}")
            a2 = parse_area_sqm(f"{v2_raw} {unit}")
            if a1 and a2:
                min_a = min(a1, a2)
                max_a = max(a1, a2)
                pref_a = round((min_a + max_a) / 2.0, 3)
                return (round(min_a, 3), pref_a, round(max_a, 3), user_dims)

        # Min area check: "min 100 sq ft", "at least 100 sq ft"
        min_pat = re.compile(
            r"(?:min|minimum|at\s+least)\s*[:\s]*([\d]+(?:\.\d+)?\s*(?:sq\.?\s*ft|sqft|ft[²2]|sqm|sq\.?\s*m|m[²2]))",
            re.I,
        )
        min_m = min_pat.search(clause)
        min_val = parse_area_sqm(min_m.group(1)) if min_m else None

        # Max area check: "max 200 sq ft", "up to 200 sq ft"
        max_pat = re.compile(
            r"(?:max|maximum|up\s+to|at\s+most)\s*[:\s]*([\d]+(?:\.\d+)?\s*(?:sq\.?\s*ft|sqft|ft[²2]|sqm|sq\.?\s*m|m[²2]))",
            re.I,
        )
        max_m = max_pat.search(clause)
        max_val = parse_area_sqm(max_m.group(1)) if max_m else None

        # Exact / preferred area: e.g. "150 sq ft", "preferred 150 sq ft"
        single_pat = re.compile(
            r"([\d]+(?:\.\d+)?\s*(?:sq\.?\s*ft|sqft|ft[²2]|sqm|sq\.?\s*m|m[²2]))",
            re.I,
        )
        single_m = single_pat.search(clause)
        pref_val = parse_area_sqm(single_m.group(1)) if single_m else None

        # If explicit dimensions were provided and no explicit area was given, derive preferred area
        if user_dims is not None and pref_val is None:
            pref_val = round(user_dims[0] * user_dims[1], 2)

        # Clean roundings
        if min_val:
            min_val = round(min_val, 3)
        if max_val:
            max_val = round(max_val, 3)
        if pref_val:
            pref_val = round(pref_val, 3)

        return (min_val, pref_val, max_val, user_dims)


    def _expand_bhk(self, text: str) -> list[RoomRequirement]:
        """Expand BHK notation (e.g. 3BHK) without inventing non-BHK rooms."""
        m = re.search(r"\b(\d+)\s*[-\s]?BHK\b", text, re.I)
        if not m:
            return []
        count = int(m.group(1))
        return [
            RoomRequirement(room_type="bedroom", min_count=count, max_count=count, source="user"),
            RoomRequirement(room_type="living", min_count=1, max_count=1, source="user"),
            RoomRequirement(room_type="kitchen", min_count=1, max_count=1, source="user"),
        ]

    def _apply_relationships(self, text: str, rooms: dict[str, RoomRequirement]) -> None:
        """Extract required/preferred adjacency and separation."""
        # Adjacency
        adj_pattern = re.compile(
            r"(\w[\w\s]*?)\s+(?:next\s+to|adjacent\s+to|near|connected?\s+to|beside|alongside|attached\s+to)\s+"
            r"(?:the\s+)?(\w[\w\s]*?)(?:[,\.;]|$|\band\b)",
            re.I,
        )
        for m in adj_pattern.finditer(text):
            r1 = self.normalizer.canonical_room_type(m.group(1))
            r2 = self.normalizer.canonical_room_type(m.group(2))
            if r1 and r2 and r1 != r2:
                if r1 in rooms and r2 not in rooms[r1].adjacency:
                    rooms[r1].adjacency.append(r2)
                if r2 in rooms and r1 not in rooms[r2].adjacency:
                    rooms[r2].adjacency.append(r1)

        # Separation
        sep_pattern = re.compile(
            r"(\w[\w\s]*?)\s+(?:away\s+from|separate\s+from|not\s+near|far\s+from|separated?\s+from)\s+"
            r"(?:the\s+)?(\w[\w\s]*?)(?:[,\.;]|$|\band\b)",
            re.I,
        )
        for m in sep_pattern.finditer(text):
            r1 = self.normalizer.canonical_room_type(m.group(1))
            r2 = self.normalizer.canonical_room_type(m.group(2))
            if r1 and r2 and r1 != r2:
                if r1 in rooms and r2 not in rooms[r1].separation:
                    rooms[r1].separation.append(r2)
                if r2 in rooms and r1 not in rooms[r2].separation:
                    rooms[r2].separation.append(r1)
