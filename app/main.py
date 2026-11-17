"""Application entry point: builds the FastAPI app and wires its routes.

Run locally with `uvicorn app.main:app --reload`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request

from app import __version__, db, mcp_server
from app.audit import audit_middleware
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.routers import (
    accounts,
    app_assistant,
    app_auth,
    app_contract,
    app_pages,
    brand,
    cards,
    cases,
    customers,
    identity,
    identity_push,
    insurance,
    notifications,
    proposals,
    registry,
    review,
    signing,
)
from app.security import require_api_key

# One line per group of endpoints, shown as the group's heading in `/docs`.
TAGS = [
    {"name": "health", "description": "Is the API up, and does it reach its database."},
    {"name": "identity", "description": "Prove who the customer is. Opens the session."},
    {"name": "customers", "description": "Who the verified customer is."},
    {"name": "accounts", "description": "Balances of the verified customer."},
    {"name": "cards", "description": "Card movements, and the temporary block."},
    {"name": "cases", "description": "Hand the customer to a person: cases and routes."},
    {"name": "insurance", "description": "Eligibility, offers with consent, proposals."},
    {"name": "notifications", "description": "What the bank writes to the customer."},
    {"name": "registry", "description": "The business behind a merchant tax ID."},
    {"name": "signing", "description": "The page a proposal link opens. No API key."},
]


def create_app(repository: db.Repository | None = None) -> FastAPI:
    """Build the app.

    A factory keeps tests isolated: each test builds its own app and passes an
    in-memory repository. In production no repository is passed and the app
    uses Supabase.
    """
    app = FastAPI(
        title="Banco Magallanes banking core",
        description="Mock banking core for a fictional retail bank, built to be called "
        "by conversational agents as tools. All data is invented. Every `/v1` route needs the "
        "`X-API-Key` header, and customer routes also need the `X-Session-Token` that identity "
        "verification returns.",
        version=__version__,
        openapi_tags=TAGS,
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
    routers = (
        identity,
        identity_push,
        customers,
        accounts,
        cards,
        cases,
        review,
        insurance,
        proposals,
        registry,
        notifications,
    )
    for module in routers:
        v1.include_router(module.router)
    app.include_router(v1)
    # The signature page is public: the customer opens it from a link, without an API key.
    app.include_router(signing.router)
    # The customer app is public too: it asks for the customer's PIN itself.
    app.include_router(app_auth.router)
    app.include_router(app_pages.router)
    app.include_router(app_contract.router)
    app.include_router(app_assistant.router)
    # The icons and the web manifest, at the root addresses browsers ask for.
    app.include_router(brand.router)
    # The MCP endpoint checks the same API key itself, in a header or as a bearer token.
    app.include_router(mcp_server.router)
    return app


app = create_app()
