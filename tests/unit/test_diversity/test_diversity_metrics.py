"""Unit tests for architectural diversity metrics and duplicate detection."""

from app.agents.diversity_agent.metrics import (
    calculate_diversity_distance,
    is_duplicate,
    is_near_duplicate,
)
from app.agents.diversity_agent.signature import DesignSignatureBuilder
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.windows import WindowIntent


def test_mandatory_architectural_diversity_comparison():
    """Verify mandatory test scenario:
    - Candidate A: Living -> Dining -> Kitchen
    - Candidate B: Living -> Corridor -> Bedroom, Dining -> Kitchen
    - Candidate C: Compact grouping
    - Candidate D: Same room adjacency as A, only window position changed
    Proves:
    - A, B, C are meaningfully different (distance > 0.25).
    - D is structurally equivalent to A (distance == 0.0 or near-duplicate).
    """
    # Candidate A: Living -> Dining -> Kitchen
    cand_a = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="r_liv",
                        room_type="living",
                        allocated_region_id="reg_1",
                        doors=[
                            DoorIntent(wall_orientation="south", connects_to="exterior", door_type="entrance"),
                            DoorIntent(wall_orientation="east", connects_to="dining", door_type="interior"),
                        ],
                        windows=[WindowIntent(wall_orientation="north")],
                    ),
                    RoomDesign(
                        id="r_din",
                        room_type="dining",
                        allocated_region_id="reg_2",
                        doors=[
                            DoorIntent(wall_orientation="west", connects_to="living", door_type="interior"),
                            DoorIntent(wall_orientation="north", connects_to="kitchen", door_type="interior"),
                        ],
                    ),
                    RoomDesign(
                        id="r_kit",
                        room_type="kitchen",
                        allocated_region_id="reg_3",
                        doors=[DoorIntent(wall_orientation="south", connects_to="dining", door_type="interior")],
                    ),
                ],
            )
        ]
    )

    # Candidate B: Living -> Corridor -> Bedroom; Dining -> Kitchen
    cand_b = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="r_liv_b",
                        room_type="living",
                        allocated_region_id="reg_1",
                        doors=[
                            DoorIntent(wall_orientation="south", connects_to="exterior", door_type="entrance"),
                            DoorIntent(wall_orientation="north", connects_to="circulation", door_type="interior"),
                        ],
                    ),
                    RoomDesign(
                        id="r_bed_b",
                        room_type="bedroom",
                        allocated_region_id="reg_4",
                        doors=[DoorIntent(wall_orientation="south", connects_to="circulation", door_type="interior")],
                    ),
                    RoomDesign(
                        id="r_din_b",
                        room_type="dining",
                        allocated_region_id="reg_2",
                        doors=[DoorIntent(wall_orientation="north", connects_to="kitchen", door_type="interior")],
                    ),
                    RoomDesign(
                        id="r_kit_b",
                        room_type="kitchen",
                        allocated_region_id="reg_3",
                        doors=[DoorIntent(wall_orientation="south", connects_to="dining", door_type="interior")],
                    ),
                ],
            )
        ]
    )

    # Candidate C: Central corridor connecting all spaces
    cand_c = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="r_liv_c",
                        room_type="living",
                        allocated_region_id="reg_1",
                        intended_shape="square",
                        doors=[
                            DoorIntent(wall_orientation="south", connects_to="exterior", door_type="entrance"),
                            DoorIntent(wall_orientation="north", connects_to="circulation", door_type="interior"),
                        ],
                    ),
                    RoomDesign(
                        id="r_din_c",
                        room_type="dining",
                        allocated_region_id="reg_2",
                        intended_shape="square",
                        doors=[DoorIntent(wall_orientation="west", connects_to="circulation", door_type="interior")],
                    ),
                    RoomDesign(
                        id="r_kit_c",
                        room_type="kitchen",
                        allocated_region_id="reg_3",
                        intended_shape="square",
                        doors=[DoorIntent(wall_orientation="east", connects_to="circulation", door_type="interior")],
                    ),
                ],
            )
        ]
    )

    # Candidate D: Same adjacency and circulation as A, ONLY window position changed from North to East
    cand_d = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="r_liv_d",
                        room_type="living",
                        allocated_region_id="reg_1",
                        doors=[
                            DoorIntent(wall_orientation="south", connects_to="exterior", door_type="entrance"),
                            DoorIntent(wall_orientation="east", connects_to="dining", door_type="interior"),
                        ],
                        windows=[WindowIntent(wall_orientation="east")],  # ONLY WINDOW ORIENTATION CHANGED
                    ),
                    RoomDesign(
                        id="r_din_d",
                        room_type="dining",
                        allocated_region_id="reg_2",
                        doors=[
                            DoorIntent(wall_orientation="west", connects_to="living", door_type="interior"),
                            DoorIntent(wall_orientation="north", connects_to="kitchen", door_type="interior"),
                        ],
                    ),
                    RoomDesign(
                        id="r_kit_d",
                        room_type="kitchen",
                        allocated_region_id="reg_3",
                        doors=[DoorIntent(wall_orientation="south", connects_to="dining", door_type="interior")],
                    ),
                ],
            )
        ]
    )

    sig_a = DesignSignatureBuilder.build(cand_a)
    sig_b = DesignSignatureBuilder.build(cand_b)
    sig_c = DesignSignatureBuilder.build(cand_c)
    sig_d = DesignSignatureBuilder.build(cand_d)

    # 1. Meaningful architectural diversity between A, B, and C
    dist_ab = calculate_diversity_distance(sig_a, sig_b)
    dist_ac = calculate_diversity_distance(sig_a, sig_c)
    dist_bc = calculate_diversity_distance(sig_b, sig_c)

    assert dist_ab >= 0.25, f"Expected meaningful diversity distance between A and B, got {dist_ab}"
    assert dist_ac >= 0.25, f"Expected meaningful diversity distance between A and C, got {dist_ac}"
    assert dist_bc >= 0.25, f"Expected meaningful diversity distance between B and C, got {dist_bc}"

    # 2. Candidate D is structurally equivalent to Candidate A (cosmetic window shift only)
    dist_ad = calculate_diversity_distance(sig_a, sig_d)
    assert dist_ad == 0.0, f"Expected D ≈ A (distance 0.0), got {dist_ad}"
    assert is_duplicate(sig_a, sig_d) is True
    assert is_near_duplicate(sig_a, sig_d, minimum_diversity_distance=0.25) is True


def test_diversity_distance_bounds_and_symmetry():
    """Verify that diversity distance is symmetric and strictly bounded in [0.0, 1.0]."""
    cand_1 = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1")],
            )
        ]
    )
    cand_2 = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="r2",
                        room_type="living",
                        allocated_region_id="reg_1",
                        intended_shape="square",
                        doors=[DoorIntent(connects_to="dining")],
                    )
                ],
            )
        ]
    )

    sig1 = DesignSignatureBuilder.build(cand_1)
    sig2 = DesignSignatureBuilder.build(cand_2)

    d12 = calculate_diversity_distance(sig1, sig2)
    d21 = calculate_diversity_distance(sig2, sig1)

    assert d12 == d21
    assert 0.0 <= d12 <= 1.0
