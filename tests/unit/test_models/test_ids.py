"""Unit tests for domain ID generation."""

from app.utils.ids import generate_id


def test_generate_id_default():
    """Verify default ID generation produces a valid non-empty string."""
    id1 = generate_id()
    assert isinstance(id1, str)
    assert len(id1) >= 8


def test_generate_id_unique():
    """Verify 1000 generated IDs are all strictly unique."""
    ids = {generate_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_generate_id_with_prefix():
    """Verify IDs generated with a prefix contain that prefix."""
    room_id = generate_id("room")
    wall_id = generate_id("wall")
    assert room_id.startswith("room_")
    assert wall_id.startswith("wall_")
    assert len(room_id) > len("room_")
