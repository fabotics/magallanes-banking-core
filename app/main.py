"""Application entry point: builds the FastAPI app and wires its routes.

Run locally with `uvicorn app.main:app --reload`.
"""

from fastapi import APIRouter, Depends, FastAPI

from app import __version__
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
    def health() -> dict[str, str]:
        """Liveness check. The database status becomes real once the repository exists."""
        return {"status": "ok", "database": "not_configured", "version": __version__}

    # Every business route is added to this router, so the API key check
    # applies to all of `/v1` without repeating it on each endpoint.
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
    app.include_router(v1)
    return app


app = create_app()
