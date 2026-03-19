from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(index=True, foreign_key="users.id")
    title: Optional[str] = Field(default="New Travel Plan", max_length=200)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(index=True, foreign_key="chat_sessions.id")
    role: str = Field(max_length=20)  # "user", "assistant", "system", "tool"
    content: str
    tool_name: Optional[str] = Field(default=None, max_length=100)
    tool_args: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class HotelBookingRequest(SQLModel, table=True):
    __tablename__ = "hotel_booking_requests"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(index=True, foreign_key="chat_sessions.id")
    user_id: str = Field(index=True, foreign_key="users.id")
    hotel_name: str
    check_in_date: str
    check_out_date: str
    room_type: Optional[str] = Field(default=None)
    guests: int = Field(default=1)
    total_price: Optional[float] = Field(default=None)
    status: str = Field(default="pending_confirmation")  # pending_confirmation, confirmed, cancelled
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    confirmed_at: Optional[datetime] = Field(default=None)
