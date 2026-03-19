from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    message: str
    requires_confirmation: bool = False
    booking_details: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class BookingConfirmationRequest(BaseModel):
    session_id: str
    booking_id: str
    is_confirmed: bool


class BookingConfirmationResponse(BaseModel):
    booking_id: str
    status: str
    message: str


class SessionResponse(BaseModel):
    id: str
    title: Optional[str] = None
    is_active: bool
    created_at: str


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]
