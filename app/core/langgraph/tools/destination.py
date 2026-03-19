import json
from typing import Optional

import structlog
from langchain_core.tools import tool

from app.core.metrics import AGENT_STEP_COUNT
from app.services.memory import cache_get, cache_set

logger = structlog.get_logger(__name__)

DESTINATIONS_DB = {
    "hanoi": {
        "name": "Hanoi",
        "country": "Vietnam",
        "description": "Vietnam's capital city blends centuries-old temples, French colonial architecture, and vibrant street food culture.",
        "highlights": [
            "Old Quarter with 36 ancient streets",
            "Ho Chi Minh Mausoleum & Temple of Literature",
            "Hoan Kiem Lake and Ngoc Son Temple",
            "Water Puppet Theatre",
            "Train Street experience",
        ],
        "best_time_to_visit": "October to April (dry season)",
        "budget_level": "budget",
        "tags": ["culture", "food", "history", "temples"],
    },
    "da nang": {
        "name": "Da Nang",
        "country": "Vietnam",
        "description": "A coastal city famous for beaches, the Golden Bridge, and as a gateway to Hoi An Ancient Town.",
        "highlights": [
            "My Khe Beach",
            "Golden Bridge at Ba Na Hills",
            "Marble Mountains",
            "Dragon Bridge",
            "Day trip to Hoi An Ancient Town",
        ],
        "best_time_to_visit": "February to May",
        "budget_level": "moderate",
        "tags": ["beach", "adventure", "sightseeing", "culture"],
    },
    "tokyo": {
        "name": "Tokyo",
        "country": "Japan",
        "description": "A mesmerizing blend of ultramodern skyscrapers, traditional temples, world-class cuisine, and cutting-edge technology.",
        "highlights": [
            "Senso-ji Temple in Asakusa",
            "Shibuya Crossing and Harajuku",
            "Tsukiji Outer Market",
            "Meiji Shrine",
            "Akihabara Electric Town",
        ],
        "best_time_to_visit": "March to May (cherry blossom) or October to November",
        "budget_level": "luxury",
        "tags": ["culture", "food", "technology", "temples", "shopping"],
    },
    "bangkok": {
        "name": "Bangkok",
        "country": "Thailand",
        "description": "Thailand's vibrant capital known for ornate shrines, bustling street life, and incredible street food.",
        "highlights": [
            "Grand Palace and Wat Phra Kaew",
            "Wat Arun (Temple of Dawn)",
            "Chatuchak Weekend Market",
            "Floating Markets",
            "Khao San Road nightlife",
        ],
        "best_time_to_visit": "November to February (cool season)",
        "budget_level": "budget",
        "tags": ["culture", "food", "temples", "shopping", "nightlife"],
    },
    "singapore": {
        "name": "Singapore",
        "country": "Singapore",
        "description": "A modern city-state blending cultures, futuristic architecture, lush gardens, and a world-renowned food scene.",
        "highlights": [
            "Gardens by the Bay and Supertree Grove",
            "Marina Bay Sands SkyPark",
            "Sentosa Island",
            "Hawker Centers (Chinatown, Maxwell)",
            "Orchard Road shopping",
        ],
        "best_time_to_visit": "February to April",
        "budget_level": "luxury",
        "tags": ["culture", "food", "shopping", "modern", "gardens"],
    },
    "dubai": {
        "name": "Dubai",
        "country": "UAE",
        "description": "A futuristic desert metropolis featuring record-breaking architecture, luxury shopping, and desert adventures.",
        "highlights": [
            "Burj Khalifa observation deck",
            "Dubai Mall and Aquarium",
            "Desert Safari experience",
            "Palm Jumeirah and Atlantis",
            "Gold and Spice Souks",
        ],
        "best_time_to_visit": "November to March",
        "budget_level": "luxury",
        "tags": ["luxury", "shopping", "adventure", "architecture"],
    },
}


@tool
async def recommend_destinations(
    interests: str,
    budget: Optional[str] = None,
    travel_month: Optional[str] = None,
) -> str:
    """Recommend attractive travel destinations based on user preferences.

    Args:
        interests: Comma-separated interests (e.g., "culture, food, beach, adventure").
        budget: Budget level - "budget", "moderate", or "luxury".
        travel_month: Preferred travel month (e.g., "March", "October").

    Returns:
        A JSON string with recommended destinations and details.
    """
    AGENT_STEP_COUNT.labels(step_name="recommend_destinations", status="started").inc()

    logger.info(
        "destination_recommendation_started",
        interests=interests,
        budget=budget,
    )

    cache_key = f"destinations:{interests}:{budget}:{travel_month}"
    cached = await cache_get(cache_key)
    if cached:
        AGENT_STEP_COUNT.labels(step_name="recommend_destinations", status="completed").inc()
        return cached

    interest_list = [i.strip().lower() for i in interests.split(",")]

    scored_destinations = []
    for key, dest in DESTINATIONS_DB.items():
        score = 0
        for interest in interest_list:
            if interest in dest["tags"]:
                score += 2
            if interest in dest["description"].lower():
                score += 1

        if budget and dest["budget_level"] == budget.lower():
            score += 1

        if score > 0:
            scored_destinations.append({
                **dest,
                "match_score": score,
            })

    scored_destinations.sort(key=lambda x: x["match_score"], reverse=True)
    top_destinations = scored_destinations[:3] if scored_destinations else list(DESTINATIONS_DB.values())[:3]

    result = json.dumps({
        "recommendations": top_destinations,
        "search_criteria": {
            "interests": interest_list,
            "budget": budget,
            "travel_month": travel_month,
        },
        "total_results": len(top_destinations),
    }, indent=2)

    await cache_set(cache_key, result, ttl=1800)
    AGENT_STEP_COUNT.labels(step_name="recommend_destinations", status="completed").inc()

    logger.info("destination_recommendation_completed", results_count=len(top_destinations))
    return result


@tool
async def get_destination_details(destination: str) -> str:
    """Get detailed information about a specific destination.

    Args:
        destination: The name of the destination city.

    Returns:
        A JSON string with detailed destination information.
    """
    AGENT_STEP_COUNT.labels(step_name="get_destination_details", status="started").inc()

    dest_lower = destination.lower()
    dest_info = DESTINATIONS_DB.get(dest_lower)

    if not dest_info:
        for key, value in DESTINATIONS_DB.items():
            if dest_lower in key or key in dest_lower:
                dest_info = value
                break

    if not dest_info:
        dest_info = {
            "name": destination,
            "country": "Unknown",
            "description": f"{destination} is a wonderful destination with much to explore.",
            "highlights": ["Local attractions", "Cultural experiences", "Cuisine"],
            "best_time_to_visit": "Year-round",
            "budget_level": "moderate",
            "tags": ["travel"],
        }

    AGENT_STEP_COUNT.labels(step_name="get_destination_details", status="completed").inc()
    return json.dumps(dest_info, indent=2)
