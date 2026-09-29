"""PlanForge AI — Application Entry Point.

Starts the PlanForge FastAPI REST API server using Uvicorn.
"""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Run the PlanForge API server."""
    uvicorn.run("app.api.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
 