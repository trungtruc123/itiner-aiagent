import json
from typing import Optional

import httpx
import structlog
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.metrics import AGENT_STEP_COUNT
from app.services.memory import cache_get, cache_set

logger = structlog.get_logger(__name__)

MOCK_WEATHER = {
    "hanoi": {"temp": 25, "condition": "Partly Cloudy", "humidity": 75},
    "da nang": {"temp": 28, "condition": "Sunny", "humidity": 70},
    "ho chi minh city": {"temp": 32, "condition": "Thunderstorms", "humidity": 80},
    "tokyo": {"temp": 18, "condition": "Clear", "humidity": 55},
    "bangkok": {"temp": 34, "condition": "Hot and Humid", "humidity": 85},
    "singapore": {"temp": 30, "condition": "Partly Cloudy", "humidity": 82},
    "dubai": {"temp": 36, "condition": "Sunny", "humidity": 40},
}


@tool
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def get_weather(
    city: str,
    date: Optional[str] = None,
) -> str:
    """Get current weather or forecast for a city.

    Args:
        city: The city name to get weather for.
        date: Optional date for forecast (YYYY-MM-DD). If not provided, returns current weather.

    Returns:
        A JSON string with weather information.
    """
    AGENT_STEP_COUNT.labels(step_name="get_weather", status="started").inc()

    logger.info("weather_lookup_started", city=city, date=date)

    cache_key = f"weather:{city}:{date or 'current'}"
    cached = await cache_get(cache_key)
    if cached:
        AGENT_STEP_COUNT.labels(step_name="get_weather", status="completed").inc()
        return cached

    weather_data = None

    if settings.WEATHER_API_KEY != "your-weather-api-key":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{settings.WEATHER_API_URL}/weather",
                    params={
                        "q": city,
                        "appid": settings.WEATHER_API_KEY,
                        "units": "metric",
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    weather_data = {
                        "city": city,
                        "temperature": data["main"]["temp"],
                        "condition": data["weather"][0]["description"],
                        "humidity": data["main"]["humidity"],
                        "wind_speed": data["wind"]["speed"],
                        "source": "openweathermap",
                    }
        except Exception:
            logger.warning("weather_api_fallback_to_mock", city=city, exc_info=True)

    if not weather_data:
        city_lower = city.lower()
        mock = MOCK_WEATHER.get(city_lower)
        if not mock:
            for key in MOCK_WEATHER:
                if city_lower in key or key in city_lower:
                    mock = MOCK_WEATHER[key]
                    break

        if mock:
            weather_data = {
                "city": city,
                "temperature": mock["temp"],
                "condition": mock["condition"],
                "humidity": mock["humidity"],
                "wind_speed": 12,
                "source": "mock_data",
            }
        else:
            weather_data = {
                "city": city,
                "temperature": 25,
                "condition": "Clear",
                "humidity": 60,
                "wind_speed": 10,
                "source": "default",
            }

    if date:
        weather_data["forecast_date"] = date
        weather_data["note"] = "Forecast data may vary. Check closer to your travel date for accuracy."

    weather_data["travel_advisory"] = _get_travel_advisory(
        weather_data["temperature"],
        weather_data["condition"],
    )

    result = json.dumps(weather_data, indent=2)
    await cache_set(cache_key, result, ttl=1800)

    AGENT_STEP_COUNT.labels(step_name="get_weather", status="completed").inc()
    logger.info("weather_lookup_completed", city=city)

    return result


def _get_travel_advisory(temperature: float, condition: str) -> str:
    condition_lower = condition.lower()

    if temperature > 35:
        return "Very hot. Stay hydrated, wear sunscreen, and avoid midday sun."
    if temperature > 30:
        return "Warm weather. Light clothing recommended. Stay hydrated."
    if temperature < 10:
        return "Cold weather. Pack warm layers and a jacket."
    if "rain" in condition_lower or "storm" in condition_lower or "thunder" in condition_lower:
        return "Rain expected. Bring an umbrella and waterproof gear."
    return "Pleasant weather for travel. Enjoy your trip!"
