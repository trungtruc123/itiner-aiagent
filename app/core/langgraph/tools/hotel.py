import json
from typing import Optional

import structlog
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.metrics import AGENT_STEP_COUNT
from app.services.memory import cache_get, cache_set

logger = structlog.get_logger(__name__)

MOCK_HOTELS = {
    "hanoi": [
        {
            "name": "Sofitel Legend Metropole Hanoi",
            "address": "15 Ngo Quyen Street, Hoan Kiem, Hanoi",
            "rating": 4.8,
            "price_per_night": 280.0,
            "room_type": "Deluxe",
            "amenities": ["spa", "pool", "restaurant", "wifi", "gym", "bar"],
        },
        {
            "name": "JW Marriott Hotel Hanoi",
            "address": "8 Do Duc Duc, Me Tri, Nam Tu Liem, Hanoi",
            "rating": 4.6,
            "price_per_night": 180.0,
            "room_type": "Superior",
            "amenities": ["pool", "restaurant", "wifi", "gym", "business_center"],
        },
        {
            "name": "Hanoi Old Quarter Homestay",
            "address": "25 Hang Bac, Hoan Kiem, Hanoi",
            "rating": 4.2,
            "price_per_night": 45.0,
            "room_type": "Standard",
            "amenities": ["wifi", "breakfast", "laundry"],
        },
    ],
    "da nang": [
        {
            "name": "InterContinental Danang Sun Peninsula Resort",
            "address": "Bai Bac, Son Tra Peninsula, Da Nang",
            "rating": 4.9,
            "price_per_night": 450.0,
            "room_type": "Ocean View Suite",
            "amenities": ["private_beach", "spa", "pool", "restaurant", "wifi", "gym"],
        },
        {
            "name": "Novotel Danang Premier Han River",
            "address": "36 Bach Dang, Hai Chau, Da Nang",
            "rating": 4.4,
            "price_per_night": 120.0,
            "room_type": "River View",
            "amenities": ["pool", "restaurant", "wifi", "gym", "bar"],
        },
    ],
    "tokyo": [
        {
            "name": "Park Hyatt Tokyo",
            "address": "3-7-1-2 Nishi Shinjuku, Shinjuku, Tokyo",
            "rating": 4.8,
            "price_per_night": 550.0,
            "room_type": "Park Suite",
            "amenities": ["spa", "pool", "restaurant", "wifi", "gym", "bar", "concierge"],
        },
        {
            "name": "Shinjuku Granbell Hotel",
            "address": "2-14-5 Kabukicho, Shinjuku, Tokyo",
            "rating": 4.1,
            "price_per_night": 95.0,
            "room_type": "Standard Double",
            "amenities": ["wifi", "restaurant", "laundry"],
        },
    ],
    "bangkok": [
        {
            "name": "Mandarin Oriental Bangkok",
            "address": "48 Oriental Avenue, Bang Rak, Bangkok",
            "rating": 4.9,
            "price_per_night": 380.0,
            "room_type": "Premier Room",
            "amenities": ["spa", "pool", "restaurant", "wifi", "gym", "river_view"],
        },
        {
            "name": "Ibis Bangkok Riverside",
            "address": "27 Charoen Nakhon Road, Bangkok",
            "rating": 4.0,
            "price_per_night": 55.0,
            "room_type": "Standard",
            "amenities": ["pool", "wifi", "restaurant", "shuttle"],
        },
    ],
    "singapore": [
        {
            "name": "Marina Bay Sands",
            "address": "10 Bayfront Avenue, Singapore",
            "rating": 4.7,
            "price_per_night": 500.0,
            "room_type": "Deluxe Room",
            "amenities": ["infinity_pool", "casino", "spa", "restaurant", "wifi", "gym"],
        },
        {
            "name": "Hotel Boss",
            "address": "500 Jalan Sultan, Singapore",
            "rating": 3.8,
            "price_per_night": 70.0,
            "room_type": "Superior",
            "amenities": ["wifi", "restaurant", "pool"],
        },
    ],
}


@tool
async def search_hotels(
    destination: str,
    check_in_date: str,
    check_out_date: str,
    max_price_per_night: Optional[float] = None,
    min_rating: Optional[float] = None,
) -> str:
    """Search for available hotels at a destination.

    Args:
        destination: The city or location to search for hotels.
        check_in_date: Check-in date (YYYY-MM-DD).
        check_out_date: Check-out date (YYYY-MM-DD).
        max_price_per_night: Optional maximum price per night in USD.
        min_rating: Optional minimum hotel rating (1-5).

    Returns:
        A JSON string with available hotel options.
    """
    AGENT_STEP_COUNT.labels(step_name="search_hotels", status="started").inc()

    logger.info(
        "hotel_search_started",
        destination=destination,
        check_in=check_in_date,
        check_out=check_out_date,
    )

    cache_key = f"hotels:{destination}:{check_in_date}:{check_out_date}"
    cached = await cache_get(cache_key)
    if cached:
        logger.info("hotel_search_cache_hit", cache_key=cache_key)
        AGENT_STEP_COUNT.labels(step_name="search_hotels", status="completed").inc()
        return cached

    destination_lower = destination.lower()
    hotels = []

    for city, city_hotels in MOCK_HOTELS.items():
        if city in destination_lower or destination_lower in city:
            hotels = city_hotels
            break

    if not hotels:
        hotels = [
            {
                "name": f"Grand Hotel {destination}",
                "address": f"Central District, {destination}",
                "rating": 4.3,
                "price_per_night": 150.0,
                "room_type": "Deluxe",
                "amenities": ["wifi", "restaurant", "pool", "gym"],
            },
            {
                "name": f"{destination} Budget Inn",
                "address": f"Tourist Area, {destination}",
                "rating": 3.8,
                "price_per_night": 60.0,
                "room_type": "Standard",
                "amenities": ["wifi", "breakfast"],
            },
        ]

    filtered_hotels = []
    for hotel in hotels:
        if max_price_per_night and hotel["price_per_night"] > max_price_per_night:
            continue
        if min_rating and hotel["rating"] < min_rating:
            continue
        filtered_hotels.append({
            **hotel,
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
        })

    result = json.dumps({
        "hotels": filtered_hotels,
        "destination": destination,
        "total_results": len(filtered_hotels),
    }, indent=2)

    await cache_set(cache_key, result, ttl=600)
    AGENT_STEP_COUNT.labels(step_name="search_hotels", status="completed").inc()

    logger.info("hotel_search_completed", results_count=len(filtered_hotels))
    return result


@tool
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def prepare_hotel_booking(
    hotel_name: str,
    check_in_date: str,
    check_out_date: str,
    room_type: str,
    guest_name: str,
    num_guests: int = 1,
    price_per_night: float = 0.0,
) -> str:
    """Prepare a hotel booking that requires user confirmation before finalizing.

    This tool creates a pending booking that must be confirmed by the user.
    The booking will NOT be finalized until the user explicitly confirms it.

    Args:
        hotel_name: Name of the hotel to book.
        check_in_date: Check-in date (YYYY-MM-DD).
        check_out_date: Check-out date (YYYY-MM-DD).
        room_type: Type of room to book.
        guest_name: Full name of the primary guest.
        num_guests: Number of guests.
        price_per_night: Price per night in USD.

    Returns:
        A JSON string with pending booking details requiring user confirmation.
    """
    AGENT_STEP_COUNT.labels(step_name="prepare_hotel_booking", status="started").inc()

    logger.info(
        "hotel_booking_preparation_started",
        hotel=hotel_name,
        guest=guest_name,
    )

    from datetime import datetime
    check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
    check_out = datetime.strptime(check_out_date, "%Y-%m-%d")
    num_nights = (check_out - check_in).days
    total_price = price_per_night * num_nights if price_per_night > 0 else num_nights * 100.0

    booking_details = {
        "booking_id": f"HTL-{hotel_name[:3].upper()}-{check_in_date.replace('-', '')}",
        "hotel_name": hotel_name,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "num_nights": num_nights,
        "room_type": room_type,
        "guest_name": guest_name,
        "num_guests": num_guests,
        "price_per_night": price_per_night if price_per_night > 0 else 100.0,
        "total_price": total_price,
        "currency": "USD",
        "status": "pending_confirmation",
        "requires_confirmation": True,
        "message": (
            f"Hotel booking prepared for {hotel_name}. "
            f"{num_nights} night(s) from {check_in_date} to {check_out_date}. "
            f"Total: ${total_price:.2f} USD. "
            "Please confirm to proceed with the reservation."
        ),
    }

    AGENT_STEP_COUNT.labels(step_name="prepare_hotel_booking", status="completed").inc()
    logger.info(
        "hotel_booking_prepared",
        booking_id=booking_details["booking_id"],
        total_price=total_price,
    )

    return json.dumps(booking_details, indent=2)


@tool
async def confirm_hotel_booking(booking_id: str) -> str:
    """Finalize a hotel booking after user confirmation.

    Args:
        booking_id: The booking ID to confirm.

    Returns:
        A JSON string with confirmed booking details.
    """
    AGENT_STEP_COUNT.labels(step_name="confirm_hotel_booking", status="started").inc()

    logger.info("hotel_booking_confirmation", booking_id=booking_id)

    confirmation = {
        "booking_id": booking_id,
        "status": "confirmed",
        "message": f"Booking {booking_id} has been confirmed successfully. You will receive a confirmation email shortly.",
        "confirmation_number": f"CONF-{booking_id}",
    }

    AGENT_STEP_COUNT.labels(step_name="confirm_hotel_booking", status="completed").inc()
    logger.info("hotel_booking_confirmed", booking_id=booking_id)

    return json.dumps(confirmation, indent=2)
