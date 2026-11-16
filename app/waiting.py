"""Waiting for an answer that a person gives somewhere else.

A caller who asks "has the customer approved yet?" would otherwise have to
ask again and again. With `wait`, the request is held until the answer
changes or the time is up, so the caller learns of it at once. The limit
stays well under what the hosting platform allows one request to last.
"""

from collections.abc import Callable
from time import monotonic, sleep
from typing import Annotated

from fastapi import Query

from app.db import Row

MAX_WAIT_SECONDS = 20
STEP_SECONDS = 1.0

Wait = Annotated[
    int,
    Query(
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Hold the request up to this many seconds while the status is pending.",
    ),
]


def until_settled(read: Callable[[], Row], settled: Callable[[Row], bool], seconds: int) -> Row:
    """Read a row again every second until `settled` says yes or `seconds` have passed."""
    deadline = monotonic() + seconds
    row = read()
    while not settled(row) and monotonic() < deadline:
        sleep(STEP_SECONDS)
        row = read()
    return row
