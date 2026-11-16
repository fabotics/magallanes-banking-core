"""One error shape for the whole API.

The caller is a voice agent, so every error carries a stable `error` code it
can branch on and a short `message` it can read aloud.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Raised anywhere in the app to answer with a status code, a code and a message."""

    def __init__(self, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Turn an ApiError into the JSON body `{"error": ..., "message": ...}`."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "message": exc.message},
    )
