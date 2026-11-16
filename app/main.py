"""Application entry point: builds the FastAPI app and wires its routes.

Run locally with `uvicorn app.main:app --reload`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI

from app import __version__, db
from app.config import Settings, get_settings
from app.errors import ApiError, api_error_handler
from app.security import require_api_key


def create_app() -> FastAPI:
    """Build the app. A factory keeps tests isolated: each test can build its own."""
    app = FastAPI(
        title="Banco Magallanes banking core",
        description="Mock banking core for a fictional retail bank, built to be called "
        "by conversational agents as tools.",
        version=__version__,
    )
    app.add_exception_handler(ApiError, api_error_handler)

    @app.get("/health", tags=["health"])
    def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
        """Liveness check, with the state of the database connection."""
        return {
            "status": "ok",
            "database": db.database_status(settings),
            "version": __version__,
        }

    # Every business route is added to this router, so the API key check
    # applies to all of `/v1` without repeating it on each endpoint.
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
    app.include_router(v1)
    return app


app = create_app()
