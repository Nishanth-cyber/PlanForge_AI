"""Structured exceptions for the export subsystem."""

from __future__ import annotations
from typing import Optional


class ExportError(Exception):
    """Base exception for all export and serialization failures."""

    def __init__(self, message: str, entity_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.entity_id = entity_id


class InvalidExportInputError(ExportError):
    """Raised when provided export data is malformed or invalid."""
    pass


class BundleExportError(ExportError):
    """Raised when project bundle generation fails."""
    pass
