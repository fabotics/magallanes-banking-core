"""Language of the customer pages: Spanish by default, English on request.

The language comes from `?lang=` in the link, else from the cookie a previous
`?lang=` left, else it is Spanish. The cookie has no expiry date, so the
choice lasts for the visit. Messages and emails to the customer are not
affected: they are always in the bank's language.
"""

from urllib.parse import urlencode

from fastapi import Request, Response

from app import texts_en, texts_es

DEFAULT = "es"
TEXTS = {"es": texts_es.TEXTS, "en": texts_en.TEXTS}
COOKIE = "mg_lang"


def pick_language(request: Request) -> str:
    """Return the language to show this visitor."""
    for choice in (request.query_params.get("lang"), request.cookies.get(COOKIE)):
        if choice in TEXTS:
            return choice
    return DEFAULT


def known(language: str | None, fallback: str) -> str:
    """Return `language` if the pages exist in it, else the fallback."""
    return language if language in TEXTS else fallback


def remember(request: Request, response: Response) -> None:
    """Keep a language chosen in the link for the rest of the visit."""
    choice = request.query_params.get("lang")
    if choice in TEXTS:
        response.set_cookie(COOKIE, choice, httponly=True, samesite="lax")


def switch_links(
    request: Request, path: str | None = None, params: dict[str, str] | None = None
) -> list[tuple[str, str]]:
    """Return one link per language to the same page, keeping the rest of the address.

    A page that answers a form passes the address and parameters of the page
    the form came from, because its own address cannot be opened with a link.
    """
    kept = params if params is not None else dict(request.query_params)
    kept = {name: value for name, value in kept.items() if name != "lang"}
    target = path or request.url.path
    return [(code, f"{target}?{urlencode({**kept, 'lang': code})}") for code in TEXTS]
