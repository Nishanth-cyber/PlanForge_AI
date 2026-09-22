"""Identifier utilities for the PlanForge pipeline."""

from __future__ import annotations
from typing import Optional
import uuid


def generate_id(prefix: Optional[str] = None) -> str:
    """Generate a unique domain object identifier.

    Args:
        prefix: Optional prefix for the identifier (e.g. 'room', 'req', 'wall').

    Returns:
        A unique string identifier formatted as '[prefix]_[hex]' or '[hex]'.
    """
    token = uuid.uuid4().hex[:12]
    if prefix:
        return f"{prefix}_{token}"
    return token
