import json
from pathlib import Path
from typing import Dict, List

import structlog
from langchain_core.documents import Document
from langchain_community.vectorstores import PGVector
from langchain_openai import OpenAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = structlog.get_logger(__name__)

HOTEL_POLICIES_DIR = Path(__file__).parent / "hotel_policies"

SAMPLE_HOTEL_POLICIES = [
    {
        "hotel_name": "Sofitel Legend Metropole Hanoi",
        "policies": {
            "check_in": "Check-in time is 14:00. Early check-in is available upon request and subject to availability (surcharge may apply).",
            "check_out": "Check-out time is 12:00. Late check-out until 18:00 can be arranged for an additional 50% of the room rate.",
            "cancellation": "Free cancellation up to 48 hours before check-in. Late cancellation or no-show will be charged one night's room rate.",
            "pet_policy": "Small pets (under 5kg) are welcome with a pet fee of $50 per stay. Pets must be leashed in common areas.",
            "extra_bed": "Extra bed available for $80 per night. Maximum 1 extra bed per room.",
            "breakfast": "Breakfast buffet included for Deluxe rooms and above. Additional guest breakfast: $35 per person.",
            "wifi": "Complimentary high-speed WiFi in all rooms and public areas.",
            "parking": "Valet parking available at $20 per day. Self-parking not available.",
            "smoking": "All rooms are non-smoking. Smoking is permitted in designated outdoor areas only. A cleaning fee of $250 will be charged for smoking in rooms.",
            "children": "Children under 6 stay free when using existing bedding. Children 6-12: $30 per night supplement.",
        },
    },
    {
        "hotel_name": "InterContinental Danang Sun Peninsula Resort",
        "policies": {
            "check_in": "Check-in time is 15:00. Guests arriving before 15:00 may use resort facilities while waiting.",
            "check_out": "Check-out time is 11:00. Late check-out until 15:00 available at 50% room rate.",
            "cancellation": "Free cancellation up to 7 days before arrival for standard bookings. Peak season (Dec-Feb): 14 days notice required.",
            "pet_policy": "Pets are not permitted at the resort.",
            "extra_bed": "Extra bed or rollaway available at $120 per night in suites only.",
            "breakfast": "Full buffet breakfast included in all room rates. In-room dining breakfast: additional $15 service charge.",
            "wifi": "Complimentary WiFi throughout the resort. Premium high-speed WiFi available at $10 per day.",
            "parking": "Complimentary parking for all guests.",
            "smoking": "Strictly non-smoking resort. Designated smoking areas available near the beach bar.",
            "children": "Children under 12 stay free. Kids club available daily 8:00-17:00 (complimentary). Babysitting: $25 per hour.",
            "pool": "Three pools open 6:00-22:00. Private beach access included. Towels provided poolside.",
        },
    },
    {
        "hotel_name": "Park Hyatt Tokyo",
        "policies": {
            "check_in": "Check-in time is 15:00. Express check-in available for World of Hyatt members.",
            "check_out": "Check-out time is 12:00. Late check-out available until 14:00 for Globalist members.",
            "cancellation": "Free cancellation up to 72 hours before check-in. Within 72 hours: first night charge applies.",
            "pet_policy": "Guide dogs and service animals only. No other pets permitted.",
            "extra_bed": "Not available due to Japanese room design standards.",
            "breakfast": "Breakfast at Girandole restaurant: ¥5,500 per person. Not included in standard room rates.",
            "wifi": "Complimentary high-speed WiFi in all rooms and public areas.",
            "parking": "Valet parking at ¥5,000 per day. Self-parking at adjacent Shinjuku Park Tower: ¥3,000 per day.",
            "smoking": "Non-smoking rooms only. Smoking floors available upon request.",
            "children": "Children under 12 stay free using existing bedding. Children's amenities provided upon request.",
            "spa": "Spa and fitness center open 6:00-22:00. Pool open 6:00-21:00. Spa treatments require advance booking.",
        },
    },
    {
        "hotel_name": "Marina Bay Sands",
        "policies": {
            "check_in": "Check-in time is 15:00. Early check-in subject to availability. Luggage storage available.",
            "check_out": "Check-out time is 11:00. Late check-out until 14:00: $100 charge. After 14:00: full night charge.",
            "cancellation": "Free cancellation up to 48 hours before arrival. Non-refundable rates available at 15% discount.",
            "pet_policy": "No pets allowed on premises. Service animals accepted with documentation.",
            "extra_bed": "Extra bed/rollaway: SGD 100 per night. Maximum 1 per room.",
            "breakfast": "Breakfast at RISE restaurant: SGD 55 per adult, SGD 28 per child (6-12). Not included in standard rates.",
            "wifi": "Complimentary WiFi in all rooms and selected public areas.",
            "parking": "Self-parking: SGD 15 per entry (max 3 hours). Overnight: SGD 30. Valet not available.",
            "smoking": "Entirely non-smoking hotel. Smoking only at designated outdoor areas.",
            "pool": "Infinity Pool (SkyPark) access for hotel guests only. Open 6:00-23:00. No outside guests permitted.",
            "casino": "Casino open 24 hours. Dress code applies. Entry fee for non-Singapore residents: free. Singapore citizens/PR: SGD 150 per day.",
        },
    },
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def ingest_hotel_policies(
    policies_data: List[Dict] | None = None,
) -> PGVector:
    logger.info("hotel_policies_ingestion_started")

    policies = policies_data or SAMPLE_HOTEL_POLICIES
    documents = []

    for hotel in policies:
        hotel_name = hotel["hotel_name"]
        for policy_type, policy_text in hotel["policies"].items():
            doc = Document(
                page_content=f"Hotel: {hotel_name}\nPolicy: {policy_type}\n{policy_text}",
                metadata={
                    "hotel_name": hotel_name,
                    "policy_type": policy_type,
                    "source": "hotel_policies",
                },
            )
            documents.append(doc)

    embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)

    vectorstore = PGVector.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name="hotel_policies",
        connection_string=settings.DATABASE_SYNC_URL,
        pre_delete_collection=True,
    )

    logger.info(
        "hotel_policies_ingestion_completed",
        total_documents=len(documents),
        total_hotels=len(policies),
    )

    return vectorstore


async def add_hotel_policy(
    hotel_name: str,
    policy_type: str,
    policy_text: str,
    vectorstore: PGVector,
) -> None:
    doc = Document(
        page_content=f"Hotel: {hotel_name}\nPolicy: {policy_type}\n{policy_text}",
        metadata={
            "hotel_name": hotel_name,
            "policy_type": policy_type,
            "source": "hotel_policies",
        },
    )
    vectorstore.add_documents([doc])
    logger.info(
        "hotel_policy_added",
        hotel_name=hotel_name,
        policy_type=policy_type,
    )


def get_sample_policies_json() -> str:
    return json.dumps(SAMPLE_HOTEL_POLICIES, indent=2)
