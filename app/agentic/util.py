"""JSON-safety and secret-redaction helpers for the agentic core (stdlib only)."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEY = re.compile(r"(api[_-]?key|token|secret|passw(or)?d|authorization|credential)", re.IGNORECASE)
REDACTED = "[redacted]"


def to_jsonable(
    obj: Any,
    *,
    max_depth: int = 6,
    max_str: int = 500,
    max_items: int = 50,
    _depth: int = 0,
) -> Any:
    """Convert ``obj`` to a small, JSON-safe structure.

    * Primitives pass through; long strings are truncated.
    * Mapping keys that look like credentials have their values replaced by ``[redacted]``.
    * Unknown objects are replaced by ``<TypeName>`` so large domain artifacts never leak into logs or the UI.
    """
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= max_str else obj[:max_str] + "...[truncated]"
    if _depth >= max_depth:
        return "[max-depth]"
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(obj.items()):
            if i >= max_items:
                out["..."] = f"{len(obj) - max_items} more"
                break
            key = str(k)
            if _SENSITIVE_KEY.search(key):
                out[key] = REDACTED
            else:
                out[key] = to_jsonable(
                    v, max_depth=max_depth, max_str=max_str, max_items=max_items, _depth=_depth + 1
                )
        return out
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = sorted(obj, key=str) if isinstance(obj, (set, frozenset)) else list(obj)
        out_list = [
            to_jsonable(v, max_depth=max_depth, max_str=max_str, max_items=max_items, _depth=_depth + 1)
            for v in items[:max_items]
        ]
        if len(items) > max_items:
            out_list.append(f"...{len(items) - max_items} more")
        return out_list
    return f"<{type(obj).__name__}>"
