"""Weather service — fetch and cache current weather from OpenWeatherMap."""

from __future__ import annotations

import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger("arlo.assistant.weather")

_cache: dict = {"data": None, "expires": 0}
CACHE_TTL = 1800  # 30 minutes


async def get_weather_context() -> str:
    """Get current weather as a string for chat context. Returns empty if unavailable."""
    if not settings.weather_api_key:
        return ""

    now = time.time()
    if _cache["data"] and now < _cache["expires"]:
        return _cache["data"]

    try:
        location = getattr(settings, "weather_location", "San Francisco,US")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q": location,
                    "appid": settings.weather_api_key,
                    "units": "imperial",
                },
            )
        if resp.status_code != 200:
            logger.warning("Weather API error: %s", resp.text[:200])
            return ""

        data = resp.json()
        temp = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        desc = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        wind = data.get("wind", {}).get("speed", 0)

        result = f"Weather ({location}): {temp:.0f}°F (feels {feels:.0f}°F), {desc}, humidity {humidity}%, wind {wind:.0f} mph"

        _cache["data"] = result
        _cache["expires"] = now + CACHE_TTL
        return result

    except Exception as e:
        logger.warning("Weather fetch failed: %s", e)
        return ""
