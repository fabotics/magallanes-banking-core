"""The bank's icons: the browser tab icon, the phone home screen icons and the web manifest.

Browsers ask for these at fixed addresses at the root of the site. The files
live in `app/static/brand`, next to the code, so they travel with the app
wherever it is deployed and the app answers for them itself. They are public
and the same for everyone, so browsers may keep them for a day.
"""

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["brand"])
FOLDER = Path(__file__).parent.parent / "static" / "brand"
# Each file is served at the root under its own name, with this content type.
FILES = {
    "favicon.ico": "image/x-icon",
    "favicon.svg": "image/svg+xml",
    "apple-touch-icon.png": "image/png",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "icon-maskable-512.png": "image/png",
    "site.webmanifest": "application/manifest+json",
}
KEEP = {"Cache-Control": "public, max-age=86400"}


def sender(name: str, media_type: str) -> Callable[[], FileResponse]:
    """Return the function that answers with one of the files."""

    def send() -> FileResponse:
        """Send the file as it is on disk."""
        return FileResponse(FOLDER / name, media_type=media_type, headers=KEEP)

    return send


for file_name, file_type in FILES.items():
    router.add_api_route(
        f"/{file_name}", sender(file_name, file_type), methods=["GET"], include_in_schema=False
    )
