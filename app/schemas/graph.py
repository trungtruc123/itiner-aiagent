from typing import Annotated, Any, Dict, List, Optional, Sequence

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class TravelPreferences(BaseModel):
    destination: Optional[str] = None
    departure_city: Optional[str] = None
    travel_dates: Optional[Dict[str, str]] = None  # {"start": "...", "end": "..."}
    budget: Optional[str] = None  # "budget", "moderate", "luxury"
    interests: List[str] = Field(default_factory=list)  # ["culture", "food", "adventure"]
    num_travelers: int = 1


class FlightInfo(BaseModel):
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    departure: Optional[str] = None
    arrival: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    price: Optional[float] = None
    currency: str = "USD"


class HotelInfo(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    price_per_night: Optional[float] = None
    room_type: Optional[str] = None
    amenities: List[str] = Field(default_factory=list)
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    total_price: Optional[float] = None


class ActivityInfo(BaseModel):
    name: str
    category: str  # "food", "culture", "adventure", "sightseeing"
    description: Optional[str] = None
    price: Optional[float] = None
    duration: Optional[str] = None
    location: Optional[str] = None


class WeatherInfo(BaseModel):
    destination: str
    temperature: Optional[float] = None
    condition: Optional[str] = None
    humidity: Optional[int] = None
    forecast: List[Dict[str, Any]] = Field(default_factory=list)


class AgentState(BaseModel):
    messages: Annotated[Sequence[AnyMessage], add_messages] = Field(default_factory=list)
    user_id: str = ""
    session_id: str = ""
    travel_preferences: Optional[TravelPreferences] = None
    flights: List[FlightInfo] = Field(default_factory=list)
    hotels: List[HotelInfo] = Field(default_factory=list)
    activities: List[ActivityInfo] = Field(default_factory=list)
    weather: Optional[WeatherInfo] = None
    selected_hotel: Optional[HotelInfo] = None
    booking_confirmed: Optional[bool] = None
    requires_human_confirmation: bool = False
    current_step: str = "intake"
    error: Optional[str] = None
    memory_context: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
