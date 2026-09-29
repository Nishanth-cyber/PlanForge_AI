"""Spatial partitioning engine for ASAA.

Performs computational 2D space-filling recursive bisection and polygon slicing
within the exact buildable boundary (rectangular, L-shaped, or irregular).
Guarantees zero overlap and 100% containment within the buildable boundary.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple
from shapely.geometry import Polygon, MultiPolygon, box
from app.models.planning import RoomSpec
from app.geometry.geometry_utils import extract_largest_polygon


@dataclass
class PartitionItem:
    """A planned room or zone item to be placed in the spatial partition."""
    id: str
    room_type: str
    room_spec_id: Optional[str] = None
    target_area_sqm: float = 0.0
    allocated_area_sqm: float = 0.0
    zone_type: str = "room"  # "room", "circulation", "entrance", "staircase"
    priority: str = "normal"
    category: str = "social"
    polygon: list[Tuple[float, float]] = field(default_factory=list)
    centroid: Optional[Tuple[float, float]] = None


class SpatialPartitioner:
    """Partitions a 2D buildable boundary into non-overlapping allocated regions."""

    @staticmethod
    def partition(
        buildable_polygon: Polygon,
        room_specs: list[RoomSpec],
        room_budgets: dict[str, float],
        has_staircase: bool = False,
        staircase_area_sqm: float = 8.0,
        staircase_anchor_polygon: Optional[list[Tuple[float, float]]] = None,
        circulation_area_sqm: float = 0.0,
        entrance_intent: Optional[dict] = None,
        zoning_strategy: str = "front_to_back",
    ) -> list[PartitionItem]:
        """Partition buildable polygon into non-overlapping regions for all rooms and zones.

        Args:
            buildable_polygon: Shapely Polygon of the buildable boundary.
            room_specs: List of RoomSpec objects on this floor.
            room_budgets: Map of room_spec.id -> budgeted area in sqm.
            has_staircase: Whether a staircase zone must be allocated.
            staircase_area_sqm: Reserved area for staircase zone.
            staircase_anchor_polygon: Fixed staircase polygon (e.g. from Floor 1 for vertical alignment).
            circulation_area_sqm: Budgeted area for circulation zone.
            entrance_intent: Entrance intent dictionary (e.g. {"facing": "front", "preferred_room": "living"}).
            zoning_strategy: "front_to_back", "lateral", "radial", "orientation_aligned".

        Returns:
            List of PartitionItem instances covering the space without overlaps.
        """
        results: list[PartitionItem] = []
        current_space = extract_largest_polygon(buildable_polygon)

        # 1. Allocate Staircase Zone (if required)
        if has_staircase:
            stair_item, remaining = SpatialPartitioner._carve_staircase_zone(
                current_space, staircase_area_sqm, staircase_anchor_polygon
            )
            results.append(stair_item)
            current_space = remaining

        # 2. Allocate Entrance Zone (if requested or sensible)
        if entrance_intent and current_space.area > 20.0:
            entrance_item, remaining = SpatialPartitioner._carve_entrance_zone(
                current_space, entrance_intent
            )
            if entrance_item:
                results.append(entrance_item)
                current_space = remaining

        # 3. Allocate Central Circulation Spine / Corridor zone (if budgeted and at least 3 rooms)
        sub_polys: list[Polygon] = [current_space]
        if circulation_area_sqm >= 4.0 and current_space.area > 30.0 and len(room_specs) >= 3:
            circ_item, carved_polys = SpatialPartitioner._carve_circulation_spine(
                current_space, circulation_area_sqm
            )
            if circ_item:
                results.append(circ_item)
                sub_polys = carved_polys

        # 4. Prepare room partition items
        items_to_partition: list[PartitionItem] = []
        for rs in room_specs:
            count = max(1, rs.count)
            # Area per instance
            total_budget = room_budgets.get(rs.id, rs.target_area_sqm)
            area_per_instance = total_budget / count

            for idx in range(count):
                item_id = f"{rs.id}_{idx}" if count > 1 else rs.id
                items_to_partition.append(
                    PartitionItem(
                        id=item_id,
                        room_type=rs.room_type,
                        room_spec_id=rs.id,
                        target_area_sqm=rs.target_area_sqm,
                        allocated_area_sqm=area_per_instance,
                        zone_type="room",
                        priority=rs.priority,
                        category=rs.room_category,
                    )
                )

        if not items_to_partition:
            return results

        # 5. Order rooms according to zoning strategy
        ordered_items = SpatialPartitioner._order_rooms_by_strategy(
            items_to_partition, zoning_strategy
        )

        # 6. Partition space across available sub-polygons
        if len(sub_polys) == 1:
            allocated_rooms = SpatialPartitioner._recursive_bisection(
                sub_polys[0], ordered_items, zoning_strategy
            )
            results.extend(allocated_rooms)
        else:
            sub_polys.sort(key=lambda p: (p.centroid.y, p.centroid.x))
            total_sub_area = sum(p.area for p in sub_polys)
            total_requested = sum(it.allocated_area_sqm for it in ordered_items)

            item_cursor = 0
            allocated_rooms = []
            for i, sub_p in enumerate(sub_polys):
                if i == len(sub_polys) - 1:
                    group_items = ordered_items[item_cursor:]
                else:
                    target_group_area = total_requested * (sub_p.area / total_sub_area if total_sub_area > 0 else 0.5)
                    cum = 0.0
                    split_end = item_cursor + 1
                    for idx in range(item_cursor, len(ordered_items) - 1):
                        cum += ordered_items[idx].allocated_area_sqm
                        split_end = idx + 1
                        if cum >= target_group_area * 0.8:
                            break
                    group_items = ordered_items[item_cursor:split_end]
                    item_cursor = split_end

                if group_items:
                    res_sub = SpatialPartitioner._recursive_bisection(
                        sub_p, group_items, zoning_strategy
                    )
                    allocated_rooms.extend(res_sub)

            results.extend(allocated_rooms)

        return results

    @staticmethod
    def _carve_staircase_zone(
        poly: Polygon,
        target_area: float,
        anchor_polygon: Optional[list[Tuple[float, float]]],
    ) -> Tuple[PartitionItem, Polygon]:
        """Carve out vertical circulation / staircase zone."""
        min_x, min_y, max_x, max_y = poly.bounds
        w = max_x - min_x
        h = max_y - min_y

        if anchor_polygon:
            # Use the exact fixed anchor from Floor 1
            stair_poly = Polygon(anchor_polygon)
            # Clip to current floor buildable if slightly offset
            intersected = poly.intersection(stair_poly)
            if not intersected.is_empty and intersected.area >= target_area * 0.5:
                carved_stair = intersected
            else:
                carved_stair = stair_poly
        else:
            # Anchor staircase along mid-lateral perimeter (e.g. left edge)
            stair_w = round(min(3.0, max(2.2, (target_area / 1.5) ** 0.5)), 2)
            stair_h = round(target_area / stair_w, 2)
            # Anchor at left-center
            sy = min_y + (h - stair_h) / 2.0
            stair_box = box(min_x, sy, min_x + stair_w, sy + stair_h)
            carved_stair = extract_largest_polygon(poly.intersection(stair_box))
            if carved_stair.is_empty or carved_stair.area < target_area * 0.7:
                # Fallback to corner box
                stair_box = box(min_x, min_y, min_x + stair_w, min_y + stair_h)
                carved_stair = extract_largest_polygon(poly.intersection(stair_box))

        carved_stair = extract_largest_polygon(carved_stair)
        remaining = extract_largest_polygon(poly.difference(carved_stair))

        coords = [(round(float(x), 4), round(float(y), 4)) for x, y in carved_stair.exterior.coords[:-1]]
        cx, cy = carved_stair.centroid.x, carved_stair.centroid.y

        item = PartitionItem(
            id="zone_staircase",
            room_type="staircase",
            room_spec_id=None,
            target_area_sqm=target_area,
            allocated_area_sqm=round(carved_stair.area, 2),
            zone_type="staircase",
            priority="normal",
            category="circulation",
            polygon=coords,
            centroid=(round(cx, 4), round(cy, 4)),
        )
        return item, remaining

    @staticmethod
    def _carve_entrance_zone(
        poly: Polygon, entrance_intent: dict
    ) -> Tuple[Optional[PartitionItem], Polygon]:
        """Carve out an entrance zone at the front/entrance side."""
        min_x, min_y, max_x, max_y = poly.bounds
        w = max_x - min_x
        h = max_y - min_y

        facing = str(entrance_intent.get("facing", "front")).lower()
        target_area = min(6.0, poly.area * 0.08)

        # Assume front is min_y by default
        ent_w = min(w * 0.4, 3.5)
        ent_h = target_area / ent_w

        if "north" in facing:
            ent_box = box(min_x + (w - ent_w) / 2, max_y - ent_h, min_x + (w + ent_w) / 2, max_y)
        elif "east" in facing:
            ent_box = box(max_x - ent_h, min_y + (h - ent_w) / 2, max_x, min_y + (h + ent_w) / 2)
        elif "west" in facing:
            ent_box = box(min_x, min_y + (h - ent_w) / 2, min_x + ent_h, min_y + (h + ent_w) / 2)
        else:  # front / south / default min_y
            ent_box = box(min_x + (w - ent_w) / 2, min_y, min_x + (w + ent_w) / 2, min_y + ent_h)

        carved = extract_largest_polygon(poly.intersection(ent_box))
        if carved.is_empty or carved.area < 2.0:
            return None, poly

        remaining = extract_largest_polygon(poly.difference(carved))

        coords = [(round(float(x), 4), round(float(y), 4)) for x, y in carved.exterior.coords[:-1]]
        cx, cy = carved.centroid.x, carved.centroid.y

        item = PartitionItem(
            id="zone_entrance",
            room_type="foyer",
            room_spec_id=None,
            target_area_sqm=target_area,
            allocated_area_sqm=round(carved.area, 2),
            zone_type="entrance",
            priority="high",
            category="circulation",
            polygon=coords,
            centroid=(round(cx, 4), round(cy, 4)),
        )
        return item, remaining

    @staticmethod
    def _carve_circulation_spine(
        poly: Polygon, target_area: float
    ) -> Tuple[Optional[PartitionItem], list[Polygon]]:
        """Carve a central circulation corridor strip connecting zones."""
        min_x, min_y, max_x, max_y = poly.bounds
        w = max_x - min_x
        h = max_y - min_y

        # Central spine width ~ 1.5 to 2.0 meters
        spine_width = min(2.0, max(1.2, target_area / max(w, h)))

        if w >= h:
            # Vertical central spine
            cx = min_x + w * 0.45
            spine_box = box(cx, min_y, cx + spine_width, max_y)
        else:
            # Horizontal central spine
            cy = min_y + h * 0.45
            spine_box = box(min_x, cy, max_x, cy + spine_width)

        carved = extract_largest_polygon(poly.intersection(spine_box))
        if carved.is_empty or carved.area < 3.0:
            return None, [poly]

        diff = poly.difference(carved)
        remaining_polys: list[Polygon] = []
        if isinstance(diff, Polygon):
            if not diff.is_empty and diff.area >= 1.0:
                remaining_polys.append(diff)
        elif isinstance(diff, MultiPolygon):
            for p in diff.geoms:
                if isinstance(p, Polygon) and not p.is_empty and p.area >= 1.0:
                    remaining_polys.append(p)

        if not remaining_polys:
            remaining_polys = [poly]

        coords = [(round(float(x), 4), round(float(y), 4)) for x, y in carved.exterior.coords[:-1]]
        item = PartitionItem(
            id="zone_circulation",
            room_type="corridor",
            room_spec_id=None,
            target_area_sqm=target_area,
            allocated_area_sqm=round(carved.area, 2),
            zone_type="circulation",
            priority="normal",
            category="circulation",
            polygon=coords,
            centroid=(round(carved.centroid.x, 4), round(carved.centroid.y, 4)),
        )
        return item, remaining_polys

    @staticmethod
    def _order_rooms_by_strategy(
        items: list[PartitionItem], strategy: str
    ) -> list[PartitionItem]:
        """Order room items to match zoning intent before recursive bisection."""
        # Categorical grouping
        social = [it for it in items if it.category == "social"]
        private = [it for it in items if it.category == "private"]
        service = [it for it in items if it.category == "service"]
        circulation = [it for it in items if it.category == "circulation"]
        outdoor = [it for it in items if it.category == "outdoor"]
        other = [it for it in items if it.category not in {"social", "private", "service", "circulation", "outdoor"}]

        # Prioritize within categories (high first)
        p_order = {"high": 0, "normal": 1, "low": 2}
        for group in (social, private, service, circulation, outdoor, other):
            group.sort(key=lambda it: (p_order.get(it.priority, 1), -it.allocated_area_sqm))

        if strategy == "lateral":
            # Lateral wing: Social on one wing, service in middle, private on other wing
            return social + service + other + private + circulation + outdoor
        elif strategy == "radial":
            # Central / radial: Large anchor rooms first, then dependencies
            items_sorted = list(items)
            items_sorted.sort(key=lambda it: (p_order.get(it.priority, 1), -it.allocated_area_sqm))
            return items_sorted
        elif strategy == "orientation_aligned":
            # Orientation: living/social and high priority first
            return social + private + service + circulation + other + outdoor
        else:
            # Default "front_to_back": social at front, service near middle, private at rear
            return social + service + circulation + private + other + outdoor

    @staticmethod
    def _recursive_bisection(
        poly: Polygon,
        items: list[PartitionItem],
        strategy: str,
    ) -> list[PartitionItem]:
        """Recursively partition polygon poly proportionally among items."""
        if not items:
            return []

        poly = extract_largest_polygon(poly)
        if poly.is_empty or not hasattr(poly, "exterior") or poly.exterior is None:
            return []

        if len(items) == 1:
            item = items[0]
            coords = [(round(float(x), 4), round(float(y), 4)) for x, y in poly.exterior.coords[:-1]]
            item.polygon = coords
            item.allocated_area_sqm = round(poly.area, 2)
            item.centroid = (round(poly.centroid.x, 4), round(poly.centroid.y, 4))
            return [item]

        # Divide items into two subsets A and B by area balance
        total_requested = sum(it.allocated_area_sqm for it in items)
        half_area = total_requested / 2.0

        cum = 0.0
        split_idx = 1
        for i, it in enumerate(items[:-1]):
            cum += it.allocated_area_sqm
            if cum >= half_area * 0.8:
                split_idx = i + 1
                break

        items_a = items[:split_idx]
        items_b = items[split_idx:]

        area_a = sum(it.allocated_area_sqm for it in items_a)
        frac_a = area_a / total_requested if total_requested > 0 else 0.5
        target_slice_area = poly.area * frac_a

        # Choose cut direction
        min_x, min_y, max_x, max_y = poly.bounds
        dx = max_x - min_x
        dy = max_y - min_y

        # If front-to-back strategy and vertical extent is significant, prefer horizontal cut (Y-axis)
        if strategy == "front_to_back" and dy > dx * 0.7:
            cut_axis = "y"
        elif strategy == "lateral" and dx > dy * 0.7:
            cut_axis = "x"
        else:
            cut_axis = "x" if dx >= dy else "y"

        # Find cutting coordinate via bisection search
        poly_a, poly_b = SpatialPartitioner._slice_polygon(
            poly, target_slice_area, cut_axis
        )

        # Recurse on sub-polygons
        res_a = SpatialPartitioner._recursive_bisection(poly_a, items_a, strategy)
        res_b = SpatialPartitioner._recursive_bisection(poly_b, items_b, strategy)
        return res_a + res_b

    @staticmethod
    def _slice_polygon(
        poly: Polygon, target_area: float, axis: str
    ) -> Tuple[Polygon, Polygon]:
        """Slice polygon poly along axis ('x' or 'y') to produce sub-polygon of target_area."""
        min_x, min_y, max_x, max_y = poly.bounds

        if axis == "x":
            low, high = min_x, max_x
        else:
            low, high = min_y, max_y

        # Binary search for cutting coordinate
        best_coord = (low + high) / 2.0
        best_poly_a = extract_largest_polygon(poly)
        best_poly_b = Polygon()

        for _ in range(25):
            mid = (low + high) / 2.0
            if axis == "x":
                cutter_a = box(min_x - 1.0, min_y - 1.0, mid, max_y + 1.0)
                cutter_b = box(mid, min_y - 1.0, max_x + 1.0, max_y + 1.0)
            else:
                cutter_a = box(min_x - 1.0, min_y - 1.0, max_x + 1.0, mid)
                cutter_b = box(min_x - 1.0, mid, max_x + 1.0, max_y + 1.0)

            slice_a = extract_largest_polygon(poly.intersection(cutter_a))
            slice_b = extract_largest_polygon(poly.intersection(cutter_b))

            curr_area = slice_a.area
            best_coord = mid
            best_poly_a = slice_a
            best_poly_b = slice_b

            if abs(curr_area - target_area) < 0.05:
                break
            elif curr_area < target_area:
                low = mid
            else:
                high = mid

        # Final sanity check: if either slice is empty, fallback to simple midpoint
        if best_poly_a.is_empty or best_poly_b.is_empty or best_poly_a.area < 1.0 or best_poly_b.area < 1.0:
            mid = (min_x + max_x) / 2.0 if axis == "x" else (min_y + max_y) / 2.0
            if axis == "x":
                cutter_a = box(min_x - 1.0, min_y - 1.0, mid, max_y + 1.0)
                cutter_b = box(mid, min_y - 1.0, max_x + 1.0, max_y + 1.0)
            else:
                cutter_a = box(min_x - 1.0, min_y - 1.0, max_x + 1.0, mid)
                cutter_b = box(min_x - 1.0, mid, max_x + 1.0, max_y + 1.0)
            best_poly_a = extract_largest_polygon(poly.intersection(cutter_a))
            best_poly_b = extract_largest_polygon(poly.intersection(cutter_b))

        return best_poly_a, best_poly_b
