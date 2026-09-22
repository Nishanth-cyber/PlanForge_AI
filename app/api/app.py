"""FastAPI application factory and instance setup for the PlanForge REST API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router


def create_app() -> FastAPI:
    """Create and configure the PlanForge FastAPI application."""
    application = FastAPI(
        title="PlanForge AI API",
        description=(
            "AI-assisted generative architectural floor-plan system. "
            "Exposes end-to-end multi-floor planning, ASAA spatial allocation, "
            "architectural intent, geometry construction, independent validation, "
            "diversity exploration, explainability tracing, and publication exports."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Enable CORS for local testing and research interfaces
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount versioned API routes
    application.include_router(router, prefix="/api/v1")

    # Also mount at root for direct convenient access
    application.include_router(router)

    # Conditionally mount compiled web UI if frontend/dist exists
    from pathlib import Path
    dist_dir = Path("frontend/dist")
    if dist_dir.exists() and dist_dir.is_dir():
        from fastapi.staticfiles import StaticFiles
        application.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")

    return application


# Global application instance for uvicorn
app = create_app()
