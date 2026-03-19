import json
from typing import Optional

import structlog
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.metrics import AGENT_STEP_COUNT
from app.services.memory import cache_get, cache_set

logger = structlog.get_logger(__name__)

MOCK_FLIGHTS = [
    {
        "airline": "Vietnam Airlines",
        "flight_number": "VN301",
        "departure": "Ho Chi Minh City (SGN)",
        "arrival": "Hanoi (HAN)",
        "departure_time": "06:00",
        "arrival_time": "08:10",
        "price": 120.0,
        "currency": "USD",
    },
    {
        "airline": "Bamboo Airways",
        "flight_number": "QH201",
        "departure": "Ho Chi Minh City (SGN)",
        "arrival": "Da Nang (DAD)",
        "departure_time": "09:30",
        "arrival_time": "10:50",
        "price": 85.0,
        "currency": "USD",
    },
    {
        "airline": "Emirates",
        "flight_number": "EK392",
        "departure": "Ho Chi Minh City (SGN)",
        "arrival": "Dubai (DXB)",
        "departure_time": "23:45",
        "arrival_time": "04:30",
        "price": 650.0,
        "currency": "USD",
    },
    {
        "airline": "Singapore Airlines",
        "flight_number": "SQ177",
        "departure": "Hanoi (HAN)",
        "arrival": "Singapore (SIN)",
        "departure_time": "14:00",
        "arrival_time": "17:30",
        "price": 280.0,
        "currency": "USD",
    },
    {
        "airline": "ANA",
        "flight_number": "NH834",
        "departure": "Ho Chi Minh City (SGN)",
        "arrival": "Tokyo Narita (NRT)",
        "departure_time": "00:05",
        "arrival_time": "07:30",
        "price": 520.0,
        "currency": "USD",
    },
    {
        "airline": "Thai Airways",
        "flight_number": "TG557",
        "departure": "Hanoi (HAN)",
        "arrival": "Bangkok (BKK)",
        "departure_time": "11:15",
        "arrival_time": "13:30",
        "price": 195.0,
        "currency": "USD",
    },
]


@tool
async def search_flights(
    departure_city: str,
    arrival_city: str,
    departure_date: str,
    return_date: Optional[str] = None,
    max_price: Optional[float] = None,
) -> str:
    """Search for available flights between two cities.

    Args:
        departure_city: The city to depart from.
        arrival_city: The destination city.
        departure_date: The departure date (YYYY-MM-DD).
        return_date: Optional return date for round trips (YYYY-MM-DD).
        max_price: Optional maximum price filter in USD.

    Returns:
        A JSON string with available flight options.
    """
    AGENT_STEP_COUNT.labels(step_name="search_flights", status="started").inc()

    logger.info(
        "flight_search_started",
        departure=departure_city,
        arrival=arrival_city,
        date=departure_date,
    )

    cache_key = f"flights:{departure_city}:{arrival_city}:{departure_date}"
    cached = await cache_get(cache_key)
    if cached:
        logger.info("flight_search_cache_hit", cache_key=cache_key)
        AGENT_STEP_COUNT.labels(step_name="search_flights", status="completed").inc()
        return cached

    departure_lower = departure_city.lower()
    arrival_lower = arrival_city.lower()

    matched_flights = []
    for flight in MOCK_FLIGHTS:
        dep_match = departure_lower in flight["departure"].lower()
        arr_match = arrival_lower in flight["arrival"].lower()
        if dep_match and arr_match:
            if max_price and flight["price"] > max_price:
                continue
            matched_flights.append({**flight, "date": departure_date})

    if not matched_flights:
        for flight in MOCK_FLIGHTS:
            arr_match = arrival_lower in flight["arrival"].lower()
            if arr_match:
                if max_price and flight["price"] > max_price:
                    continue
                matched_flights.append({
                    **flight,
                    "departure": f"{departure_city}",
                    "date": departure_date,
                })

    if not matched_flights:
        matched_flights = [
            {
                "airline": "Sky Travel",
                "flight_number": "ST100",
                "departure": departure_city,
                "arrival": arrival_city,
                "departure_time": "08:00",
                "arrival_time": "12:00",
                "price": 350.0,
                "currency": "USD",
                "date": departure_date,
            },
            {
                "airline": "Global Air",
                "flight_number": "GA250",
                "departure": departure_city,
                "arrival": arrival_city,
                "departure_time": "15:30",
                "arrival_time": "19:30",
                "price": 420.0,
                "currency": "USD",
                "date": departure_date,
            },
        ]

    result = json.dumps({
        "flights": matched_flights,
        "search_params": {
            "departure": departure_city,
            "arrival": arrival_city,
            "date": departure_date,
            "return_date": return_date,
        },
        "total_results": len(matched_flights),
    }, indent=2)

    await cache_set(cache_key, result, ttl=600)
    AGENT_STEP_COUNT.labels(step_name="search_flights", status="completed").inc()

    logger.info(
        "flight_search_completed",
        results_count=len(matched_flights),
    )
    return result


@tool
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def book_flight(
    flight_number: str,
    passenger_name: str,
    departure_date: str,
) -> str:
    """Book a specific flight for a passenger.

    Args:
        flight_number: The flight number to book.
        passenger_name: Full name of the passenger.
        departure_date: The departure date (YYYY-MM-DD).

    Returns:
        A JSON string with booking confirmation details.
    """
    AGENT_STEP_COUNT.labels(step_name="book_flight", status="started").inc()

    logger.info(
        "flight_booking_started",
        flight_number=flight_number,
        passenger=passenger_name,
    )

    booking = {
        "booking_id": f"FLT-{flight_number}-{departure_date.replace('-', '')}",
        "flight_number": flight_number,
        "passenger_name": passenger_name,
        "departure_date": departure_date,
        "status": "confirmed",
        "message": f"Flight {flight_number} booked successfully for {passenger_name} on {departure_date}.",
    }

    AGENT_STEP_COUNT.labels(step_name="book_flight", status="completed").inc()
    logger.info("flight_booking_completed", booking_id=booking["booking_id"])

    return json.dumps(booking, indent=2)
