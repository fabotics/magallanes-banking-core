"""Application entry point: builds the FastAPI app and wires its routes.

Run locally with `uvicorn app.main:app --reload`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request

from app import __version__, db
from app.audit import audit_middleware
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.routers import accounts, cards, cases, customers, identity
from app.security import require_api_key


def create_app(repository: db.Repository | None = None) -> FastAPI:
    """Build the app.

    A factory keeps tests isolated: each test builds its own app and passes an
    in-memory repository. In production no repository is passed and the app
    uses Supabase.
    """
    app = FastAPI(
        title="Banco Magallanes banking core",
        description="Mock banking core for a fictional retail bank, built to be called "
        "by conversational agents as tools.",
        version=__version__,
    )
    app.state.repository = repository
    register_error_handlers(app)
    app.middleware("http")(audit_middleware)

    @app.get("/health", tags=["health"])
    def health(
        request: Request, settings: Annotated[Settings, Depends(get_settings)]
    ) -> dict[str, str]:
        """Liveness check, with the state of the database connection."""
        return {
            "status": "ok",
            "database": db.database_status(request.app, settings),
            "version": __version__,
        }

    # Every business route is added to this router, so the API key check
    # applies to all of `/v1` without repeating it on each endpoint.
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
    for module in (identity, customers, accounts, cards, cases):
        v1.include_router(module.router)
    app.include_router(v1)
    return app


app = create_app()
