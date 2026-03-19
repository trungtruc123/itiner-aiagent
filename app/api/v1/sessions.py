from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_current_user, get_db
from app.models.session import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import ChatHistoryResponse, SessionListResponse, SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()

    return SessionListResponse(
        sessions=[
            SessionResponse(
                id=s.id,
                title=s.title,
                is_active=s.is_active,
                created_at=s.created_at.isoformat(),
            )
            for s in sessions
        ]
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_user_session(db, session_id, current_user.id)
    return SessionResponse(
        id=session.id,
        title=session.title,
        is_active=session.is_active,
        created_at=session.created_at.isoformat(),
    )


@router.get("/{session_id}/history", response_model=ChatHistoryResponse)
async def get_session_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_session(db, session_id, current_user.id)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()

    return ChatHistoryResponse(
        session_id=session_id,
        messages=[
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_name": m.tool_name,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_user_session(db, session_id, current_user.id)
    session.is_active = False
    db.add(session)


async def _get_user_session(
    db: AsyncSession, session_id: str, user_id: str
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return session
