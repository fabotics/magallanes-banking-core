"""Repository: every database call lives here.

The rest of the app talks to a `Repository`, a small set of table operations,
and never to the Supabase client. That is what lets the tests create the app
with an in-memory repository and run without a network.
"""

from functools import lru_cache
from typing import Annotated, Any, Protocol

from fastapi import Depends, FastAPI, Request
from supabase import Client, create_client

from app.config import Settings, get_settings
from app.errors import ApiError

Row = dict[str, Any]


class Repository(Protocol):
    """The table operations the app needs. Filters are exact matches on columns."""

    def select(self, table: str, filters: Row | None = None) -> list[Row]: ...

    def insert(self, table: str, row: Row) -> Row: ...

    def insert_many(self, table: str, rows: list[Row]) -> list[Row]: ...

    def update(self, table: str, filters: Row, values: Row) -> list[Row]: ...

    def delete_all(self, table: str, key: str = "id") -> None: ...

    def ping(self) -> bool: ...


class SupabaseRepository:
    """Repository backed by Postgres on Supabase, through its REST client."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def select(self, table: str, filters: Row | None = None) -> list[Row]:
        """Return the rows of `table` whose columns equal the given filters."""
        query = self._client.table(table).select("*")
        for column, value in (filters or {}).items():
            query = query.eq(column, value)
        return query.execute().data

    def insert(self, table: str, row: Row) -> Row:
        """Insert one row and return it as stored, with database defaults filled in."""
        return self.insert_many(table, [row])[0]

    def insert_many(self, table: str, rows: list[Row]) -> list[Row]:
        """Insert several rows in one request and return them as stored."""
        if not rows:
            return []
        return self._client.table(table).insert(rows).execute().data

    def update(self, table: str, filters: Row, values: Row) -> list[Row]:
        """Set `values` on the rows matching `filters` and return the updated rows."""
        query = self._client.table(table).update(values)
        for column, value in filters.items():
            query = query.eq(column, value)
        return query.execute().data

    def delete_all(self, table: str, key: str = "id") -> None:
        """Delete every row. The API refuses a delete without a filter, hence `key`."""
        self._client.table(table).delete().not_.is_(key, "null").execute()

    def ping(self) -> bool:
        """Return True when a trivial read succeeds."""
        try:
            self._client.table("insurance_products").select("code").limit(1).execute()
        except Exception:
            return False
        return True


@lru_cache
def _client(url: str, key: str) -> Client:
    """Create the Supabase client once per process and reuse it."""
    return create_client(url, key)


def build_repository(settings: Settings) -> Repository:
    """Return the Supabase repository, or answer HTTP 503 if it is not configured."""
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise ApiError(503, "database_not_configured", "The database is not configured.")
    return SupabaseRepository(_client(settings.supabase_url, settings.supabase_secret_key))


def repository_for(app: FastAPI, settings: Settings) -> Repository:
    """Return the repository the app was created with (tests), else the Supabase one."""
    return app.state.repository or build_repository(settings)


def get_repository(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> Repository:
    """Dependency that hands the repository to an endpoint."""
    return repository_for(request.app, settings)


def database_status(app: FastAPI, settings: Settings) -> str:
    """Describe the database for the health check: ok, unreachable or not_configured."""
    try:
        repository = repository_for(app, settings)
    except ApiError:
        return "not_configured"
    return "ok" if repository.ping() else "unreachable"
