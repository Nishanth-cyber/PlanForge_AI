"""Unit tests for DesignSignature extraction and canonical normalization."""

from app.agents.diversity_agent.signature import DesignSignatureBuilder
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.staircase import StaircaseIntent
from app.models.windows import WindowIntent


def test_design_signature_creation_and_normalization():
    """Verify that DesignSignature extracts structural connectivity and ignores IDs/timestamps."""
    dset = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="room_123_custom",
                        room_type="living",
                        allocated_region_id="reg_1",
                        intended_dimensions=(4.0, 5.0),
                        intended_shape="rectangular",
                        doors=[
                            DoorIntent(wall_orientation="south", connects_to="exterior", door_type="entrance"),
                            DoorIntent(wall_orientation="east", connects_to="dining", door_type="interior"),
                        ],
                    ),
                    RoomDesign(
                        id="room_456_custom",
                        room_type="dining",
                        allocated_region_id="reg_2",
                        intended_dimensions=(3.0, 4.0),
                        intended_shape="rectangular",
                        doors=[
                            DoorIntent(wall_orientation="west", connects_to="living", door_type="interior"),
                            DoorIntent(wall_orientation="north", connects_to="kitchen", door_type="interior"),
                        ],
                    ),
                    RoomDesign(
                        id="room_789_custom",
                        room_type="kitchen",
                        allocated_region_id="reg_3",
                        intended_dimensions=(3.0, 3.0),
                        intended_shape="square",
                        doors=[
                            DoorIntent(wall_orientation="south", connects_to="dining", door_type="interior"),
                        ],
                    ),
                ],
            )
        ]
    )

    sig = DesignSignatureBuilder.build(dset)

    # Invariants
    assert sig.entrance_room_type == "living"
    assert sig.circulation_type == "direct"
    assert ("dining", "living") in sig.adjacency_edges
    assert ("dining", "kitchen") in sig.adjacency_edges
    assert sig.social_sequence == ("living", "dining", "kitchen")
    assert dict(sig.room_shapes)["kitchen"] == "square"
    assert dict(sig.proportion_buckets)["kitchen"] == "square"


def test_signature_circulation_classification():
    """Verify corridor vs direct vs hybrid classification."""
    # Corridor-centric design
    corr_dset = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="r_liv",
                        room_type="living",
                        allocated_region_id="reg_liv",
                        doors=[DoorIntent(connects_to="circulation", door_type="interior")],
                    ),
                    RoomDesign(
                        id="r_din",
                        room_type="dining",
                        allocated_region_id="reg_din",
                        doors=[DoorIntent(connects_to="circulation", door_type="interior")],
                    ),
                    RoomDesign(
                        id="r_bed",
                        room_type="bedroom",
                        allocated_region_id="reg_bed",
                        doors=[DoorIntent(connects_to="circulation", door_type="interior")],
                    ),
                ],
            )
        ]
    )

    sig_corr = DesignSignatureBuilder.build(corr_dset)
    assert sig_corr.circulation_type == "corridor"


def test_signature_staircase_relationship():
    """Verify staircase core relationship in multi-floor signatures."""
    dset = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1")],
                staircase_intent=StaircaseIntent(from_floor=1, to_floor=2),
            )
        ]
    )
    sig = DesignSignatureBuilder.build(dset)
    assert sig.staircase_relationship == "circulation_core"
