"""Timezone-aware helpers.

The API container runs in UTC, but users experience time in their local
zone (configured via ``settings.user_timezone``). Naive ``date.today()``
drifts across the midnight boundary, which would cause meals logged at
9 PM PST to be filed under tomorrow's date and mysteriously vanish from
the current day's macros. Use ``user_today()`` whenever you need the
user's wall-clock day.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def user_today() -> date:
    """Return today's date in the user's configured timezone."""
    try:
        return datetime.now(tz=ZoneInfo(settings.user_timezone)).date()
    except Exception:
        return date.today()


def user_now() -> datetime:
    """Return now in the user's configured timezone."""
    try:
        return datetime.now(tz=ZoneInfo(settings.user_timezone))
    except Exception:
        return datetime.now()
