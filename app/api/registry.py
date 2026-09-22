"""Process-local in-memory project registry storing generated project results."""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from app.orchestration.pipeline import PipelineResult


class ProjectRegistry:
    """Thread-safe, process-local registry caching generated project results.

    Limitation Note:
    Project results are process-local and are not persistent across server restarts.
    Physical export bundles saved in the filesystem (e.g. outputs/<project_id>/)
    remain persistent on disk.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._projects: Dict[str, PipelineResult] = {}

    def save_result(self, result: PipelineResult) -> None:
        """Store a pipeline result by its project_id."""
        with self._lock:
            self._projects[result.project_id] = result

    def get_result(self, project_id: str) -> Optional[PipelineResult]:
        """Retrieve a stored pipeline result by its project_id."""
        with self._lock:
            return self._projects.get(project_id)

    def list_projects(self) -> List[str]:
        """Return a list of all stored project IDs."""
        with self._lock:
            return list(self._projects.keys())

    def delete_project(self, project_id: str) -> bool:
        """Remove a stored project result by its project_id."""
        with self._lock:
            return self._projects.pop(project_id, None) is not None

    def clear(self) -> None:
        """Clear all stored project results (useful for test isolation)."""
        with self._lock:
            self._projects.clear()


# Global default registry instance for API dependency injection
_DEFAULT_REGISTRY = ProjectRegistry()


def get_default_registry() -> ProjectRegistry:
    """Return the global default project registry instance."""
    return _DEFAULT_REGISTRY
