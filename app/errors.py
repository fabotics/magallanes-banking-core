"""One error shape for the whole API.

The caller is a voice agent, so every error carries a stable `error` code it
can branch on and a short `message` it can read aloud.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class ApiError(Exception):
    """Raised anywhere in the app to answer with a status code, a code and a message."""

    def __init__(self, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message


def error_body(status_code: int, error: str, message: str) -> JSONResponse:
    """Build the JSON answer `{"error": ..., "message": ...}`."""
    return JSONResponse(status_code=status_code, content={"error": error, "message": message})


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Answer for errors raised by this app."""
    return error_body(exc.status_code, exc.error, exc.message)


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Answer for framework errors such as an unknown path or a wrong method."""
    error = "not_found" if exc.status_code == 404 else "http_error"
    return error_body(exc.status_code, error, str(exc.detail))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Answer for a request that does not match the endpoint's schema: name the first problem."""
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"])
    return error_body(422, "invalid_request", f"{field}: {first['msg']}")


def register_error_handlers(app: FastAPI) -> None:
    """Attach the three handlers so every error leaves in the same shape."""
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
