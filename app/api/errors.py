"""API error definitions and path safety utilities."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

from fastapi import HTTPException, status


class PathTraversalSecurityError(HTTPException):
    """Raised when an unauthorized path traversal sequence is detected."""

    def __init__(self, detail: str = "Access denied: Path traversal outside bundle root is forbidden."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def resolve_safe_path(base_dir: Union[str, Path], relative_path: str) -> Path:
    """Resolve and verify that a relative path stays strictly within base_dir.

    Raises:
        PathTraversalSecurityError: If the target path escapes base_dir.
        HTTPException: If the file does not exist.
    """
    # Reject suspicious traversal sequences immediately
    norm_rel = relative_path.replace("\\", "/")
    if "../" in norm_rel or norm_rel.startswith("/") or norm_rel.startswith(".."):
        raise PathTraversalSecurityError("Invalid path syntax: directory traversal detected.")

    base = Path(base_dir).resolve()
    target = (base / relative_path).resolve()

    try:
        # Check if target is inside base
        target.relative_to(base)
    except ValueError as e:
        raise PathTraversalSecurityError(f"Access denied: path escapes bundle root.") from e

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requested export file '{relative_path}' was not found.",
        )

    return target
