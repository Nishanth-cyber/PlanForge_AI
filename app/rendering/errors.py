"""Structured exceptions for the rendering subsystem."""

from __future__ import annotations
from typing import Optional


class RenderingError(Exception):
    """Base exception for all floor plan rendering failures."""

    def __init__(self, message: str, entity_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.entity_id = entity_id


class UnsupportedGeometryError(RenderingError):
    """Raised when an unrenderable or corrupt geometric entity is encountered."""
    pass


class EmptyGeometryError(RenderingError):
    """Raised when a floor plan has no rooms, walls, or boundary to render."""
    pass
