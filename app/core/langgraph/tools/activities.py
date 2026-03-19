import json
from typing import Optional

import structlog
from langchain_core.tools import tool

from app.core.metrics import AGENT_STEP_COUNT
from app.services.memory import cache_get, cache_set

logger = structlog.get_logger(__name__)

ACTIVITIES_DB = {
    "hanoi": {
        "food": [
            {
                "name": "Old Quarter Street Food Tour",
                "category": "food",
                "description": "Walk through Hanoi's 36 ancient streets tasting pho, bun cha, banh mi, and egg coffee.",
                "price": 35.0,
                "duration": "3 hours",
                "location": "Hoan Kiem District",
            },
            {
                "name": "Vietnamese Cooking Class",
                "category": "food",
                "description": "Learn to cook authentic Vietnamese dishes with a local chef at a traditional home kitchen.",
                "price": 45.0,
                "duration": "4 hours",
                "location": "Ba Dinh District",
            },
        ],
        "culture": [
            {
                "name": "Temple of Literature & Imperial Citadel Tour",
                "category": "culture",
                "description": "Explore Vietnam's oldest university and the ancient imperial citadel of Thang Long.",
                "price": 25.0,
                "duration": "4 hours",
                "location": "Dong Da District",
            },
            {
                "name": "Water Puppet Show",
                "category": "culture",
                "description": "Watch the iconic Vietnamese water puppet performance at Thang Long Theatre.",
                "price": 10.0,
                "duration": "1 hour",
                "location": "Hoan Kiem District",
            },
        ],
        "adventure": [
            {
                "name": "Ha Long Bay Day Cruise",
                "category": "adventure",
                "description": "Cruise through UNESCO-listed Ha Long Bay with kayaking and cave exploration.",
                "price": 85.0,
                "duration": "Full day",
                "location": "Ha Long Bay (3.5h from Hanoi)",
            },
        ],
    },
    "tokyo": {
        "food": [
            {
                "name": "Tsukiji Market Sushi Experience",
                "category": "food",
                "description": "Taste the freshest sushi and seafood at Tokyo's famous outer market.",
                "price": 60.0,
                "duration": "2 hours",
                "location": "Chuo, Tokyo",
            },
            {
                "name": "Ramen Alley Tasting Tour",
                "category": "food",
                "description": "Sample different styles of ramen across Tokyo's best ramen shops.",
                "price": 40.0,
                "duration": "3 hours",
                "location": "Shinjuku, Tokyo",
            },
        ],
        "culture": [
            {
                "name": "Traditional Tea Ceremony",
                "category": "culture",
                "description": "Experience an authentic Japanese tea ceremony in a historic tea house.",
                "price": 50.0,
                "duration": "1.5 hours",
                "location": "Uji, Kyoto (day trip)",
            },
            {
                "name": "Senso-ji Temple & Asakusa Walking Tour",
                "category": "culture",
                "description": "Explore Tokyo's oldest temple and the traditional Asakusa neighborhood.",
                "price": 20.0,
                "duration": "3 hours",
                "location": "Taito, Tokyo",
            },
        ],
    },
    "bangkok": {
        "food": [
            {
                "name": "Chinatown Street Food Adventure",
                "category": "food",
                "description": "Explore Yaowarat Road's legendary street food stalls with pad thai, mango sticky rice, and more.",
                "price": 30.0,
                "duration": "3 hours",
                "location": "Yaowarat Road, Bangkok",
            },
        ],
        "culture": [
            {
                "name": "Grand Palace & Wat Pho Tour",
                "category": "culture",
                "description": "Visit the magnificent Grand Palace and the Temple of the Reclining Buddha.",
                "price": 20.0,
                "duration": "4 hours",
                "location": "Phra Nakhon, Bangkok",
            },
            {
                "name": "Floating Market Experience",
                "category": "culture",
                "description": "Visit Damnoen Saduak floating market for a traditional Thai market experience.",
                "price": 45.0,
                "duration": "Half day",
                "location": "Ratchaburi Province",
            },
        ],
    },
    "da nang": {
        "food": [
            {
                "name": "Central Vietnamese Food Tour",
                "category": "food",
                "description": "Taste mi quang, banh xeo, and cao lau in Da Nang and Hoi An.",
                "price": 30.0,
                "duration": "3 hours",
                "location": "Da Nang & Hoi An",
            },
        ],
        "culture": [
            {
                "name": "Hoi An Ancient Town Walking Tour",
                "category": "culture",
                "description": "Explore the UNESCO-listed ancient trading port with lantern-lit streets.",
                "price": 15.0,
                "duration": "3 hours",
                "location": "Hoi An",
            },
        ],
        "adventure": [
            {
                "name": "Ba Na Hills & Golden Bridge",
                "category": "adventure",
                "description": "Visit the famous Golden Bridge held by giant stone hands at Ba Na Hills.",
                "price": 40.0,
                "duration": "Full day",
                "location": "Ba Na Hills",
            },
        ],
    },
    "singapore": {
        "food": [
            {
                "name": "Hawker Center Food Trail",
                "category": "food",
                "description": "Visit Maxwell, Chinatown Complex, and Lau Pa Sat hawker centers for laksa, chicken rice, and chilli crab.",
                "price": 25.0,
                "duration": "3 hours",
                "location": "Chinatown, Singapore",
            },
        ],
        "culture": [
            {
                "name": "Gardens by the Bay Night Show",
                "category": "culture",
                "description": "Witness the spectacular Supertree light and sound show at Gardens by the Bay.",
                "price": 20.0,
                "duration": "2 hours",
                "location": "Marina Bay, Singapore",
            },
        ],
    },
}


@tool
async def recommend_activities(
    destination: str,
    category: Optional[str] = None,
    budget: Optional[str] = None,
) -> str:
    """Recommend activities, food experiences, and cultural attractions at a destination.

    Args:
        destination: The destination city.
        category: Optional category filter - "food", "culture", "adventure", "sightseeing".
        budget: Optional budget level - "budget", "moderate", "luxury".

    Returns:
        A JSON string with recommended activities.
    """
    AGENT_STEP_COUNT.labels(step_name="recommend_activities", status="started").inc()

    logger.info(
        "activity_recommendation_started",
        destination=destination,
        category=category,
    )

    cache_key = f"activities:{destination}:{category}:{budget}"
    cached = await cache_get(cache_key)
    if cached:
        AGENT_STEP_COUNT.labels(step_name="recommend_activities", status="completed").inc()
        return cached

    dest_lower = destination.lower()
    dest_activities = None

    for key in ACTIVITIES_DB:
        if dest_lower in key or key in dest_lower:
            dest_activities = ACTIVITIES_DB[key]
            break

    if not dest_activities:
        dest_activities = {
            "food": [{
                "name": f"{destination} Local Food Tour",
                "category": "food",
                "description": f"Explore the best local cuisine in {destination}.",
                "price": 35.0,
                "duration": "3 hours",
                "location": f"City Center, {destination}",
            }],
            "culture": [{
                "name": f"{destination} Cultural Walking Tour",
                "category": "culture",
                "description": f"Discover the cultural highlights of {destination}.",
                "price": 20.0,
                "duration": "3 hours",
                "location": f"Historic District, {destination}",
            }],
        }

    activities = []
    if category:
        cat_lower = category.lower()
        if cat_lower in dest_activities:
            activities = dest_activities[cat_lower]
    else:
        for cat_activities in dest_activities.values():
            activities.extend(cat_activities)

    if budget:
        budget_limits = {"budget": 30, "moderate": 60, "luxury": float("inf")}
        max_price = budget_limits.get(budget.lower(), float("inf"))
        activities = [a for a in activities if a["price"] <= max_price]

    result = json.dumps({
        "activities": activities,
        "destination": destination,
        "category": category,
        "total_results": len(activities),
    }, indent=2)

    await cache_set(cache_key, result, ttl=1800)
    AGENT_STEP_COUNT.labels(step_name="recommend_activities", status="completed").inc()

    logger.info("activity_recommendation_completed", results_count=len(activities))
    return result
