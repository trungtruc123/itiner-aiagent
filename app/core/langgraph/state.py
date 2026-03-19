from typing import Annotated, Any, Dict, List, Optional, Sequence

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class TravelAgentState(BaseModel):
    """State schema for the travel planning agent workflow."""

    messages: Annotated[Sequence[AnyMessage], add_messages] = Field(default_factory=list)
    user_id: str = ""
    session_id: str = ""
    memory_context: str = ""
    pending_booking: Optional[Dict[str, Any]] = None
    booking_confirmed: Optional[bool] = None
    requires_human_confirmation: bool = False
    current_step: str = "agent"
    error: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
