import json
from datetime import datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_current_user, get_db
from app.core.langgraph.graph import create_compiled_graph
from app.models.session import ChatMessage, ChatSession, HotelBookingRequest
from app.models.user import User
from app.schemas.chat import (
    BookingConfirmationRequest,
    BookingConfirmationResponse,
    ChatRequest,
    ChatResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def send_message(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get or create session
    if body.session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == body.session_id,
                ChatSession.user_id == current_user.id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
    else:
        session = ChatSession(user_id=current_user.id)
        db.add(session)
        await db.flush()

    # Save user message
    # user_msg = ChatMessage(
    #     session_id=session.id,
    #     role="user",
    #     content=body.message,
    # )
    # db.add(user_msg)
    # await db.flush()

    # Run the LangGraph agent
    try:
        graph = await create_compiled_graph()

        thread_config = {"configurable": {"thread_id": session.id}}

        # Load conversation history from this session
        history_result = await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session.id
            )
            .order_by(ChatMessage.created_at.asc())
        )
        previous_messages = history_result.scalars().all()

        history_messages = []
        for msg in previous_messages:
            if msg.role == "user":
                history_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                history_messages.append(AIMessage(content=msg.content))

        # Append current user message
        history_messages.append(HumanMessage(content=body.message))

        input_state = {
            "messages": history_messages,
            "user_id": current_user.id,
            "session_id": session.id,
        }

        result = await graph.ainvoke(input_state, config=thread_config)

        # Extract the last AI message from the result
        ai_content = ""
        requires_confirmation = False
        booking_details = None
        tool_calls_info = []

        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                ai_content = msg.content
                if msg.tool_calls:
                    tool_calls_info = [
                        {"name": tc["name"], "args": tc["args"]}
                        for tc in msg.tool_calls
                    ]
                break

        # Check for pending booking
        pending = result.get("pending_booking")
        if pending:
            requires_confirmation = True
            booking_details = pending

            # Persist booking request to DB
            booking = HotelBookingRequest(
                id=pending.get("booking_id", str(uuid4())),
                session_id=session.id,
                user_id=current_user.id,
                hotel_name=pending.get("hotel_name", ""),
                check_in_date=pending.get("check_in_date", ""),
                check_out_date=pending.get("check_out_date", ""),
                room_type=pending.get("room_type"),
                guests=pending.get("guests", 1),
                total_price=pending.get("total_price"),
                status="pending_confirmation",
            )
            db.add(booking)

        # Save assistant message
        # if ai_content:
        #     assistant_msg = ChatMessage(
        #         session_id=session.id,
        #         role="assistant",
        #         content=ai_content,
        #     )
        #     db.add(assistant_msg)

        # Update session timestamp
        session.updated_at = datetime.utcnow()

        logger.info(
            "chat_message_processed",
            session_id=session.id,
            user_id=current_user.id,
            requires_confirmation=requires_confirmation,
        )

        return ChatResponse(
            session_id=session.id,
            message=ai_content or "I'm processing your request...",
            requires_confirmation=requires_confirmation,
            booking_details=booking_details,
            tool_calls=tool_calls_info or None,
        )

    except Exception as exc:
        logger.exception(
            "chat_processing_failed",
            session_id=session.id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process your message. Please try again.",
        )


@router.post("/confirm", response_model=BookingConfirmationResponse)
async def confirm_booking(
    body: BookingConfirmationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify session belongs to user
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == body.session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Find the pending booking
    result = await db.execute(
        select(HotelBookingRequest).where(
            HotelBookingRequest.id == body.booking_id,
            HotelBookingRequest.session_id == body.session_id,
            HotelBookingRequest.user_id == current_user.id,
            HotelBookingRequest.status == "pending_confirmation",
        )
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending booking not found",
        )

    if body.is_confirmed:
        booking.status = "confirmed"
        booking.confirmed_at = datetime.utcnow()
        status_text = "confirmed"
        message = f"Hotel booking at {booking.hotel_name} has been confirmed!"
    else:
        booking.status = "cancelled"
        status_text = "cancelled"
        message = "Hotel booking has been cancelled."

    db.add(booking)

    # Resume graph with user confirmation
    try:
        confirmation_text = "confirm" if body.is_confirmed else "cancel"
        graph = await create_compiled_graph()
        thread_config = {"configurable": {"thread_id": body.session_id}}

        await graph.ainvoke(
            {"messages": [HumanMessage(content=confirmation_text)]},
            config=thread_config,
        )
    except Exception:
        logger.exception(
            "graph_resume_failed",
            session_id=body.session_id,
            booking_id=body.booking_id,
        )

    # Save assistant response
    assistant_msg = ChatMessage(
        session_id=body.session_id,
        role="assistant",
        content=message,
    )
    db.add(assistant_msg)

    logger.info(
        "booking_confirmation_processed",
        booking_id=body.booking_id,
        status=status_text,
    )

    return BookingConfirmationResponse(
        booking_id=booking.id,
        status=status_text,
        message=message,
    )
