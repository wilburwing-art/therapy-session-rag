"""Video chat API endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.v1.dependencies import Auth
from src.core.config import get_settings
from src.core.database import DbSession, get_db_session
from src.core.exceptions import NotFoundError
from src.core.security import is_valid_api_key_format, verify_api_key
from src.models.db.api_key import ApiKey
from src.models.db.organization import Organization
from src.models.db.session import Session
from src.services.video_room_service import get_video_room_service

router = APIRouter()


class TurnCredentials(BaseModel):
    """TURN server credentials for WebRTC."""

    ice_servers: list[dict[str, Any]] = Field(
        ..., description="ICE server configuration"
    )


class RoomStatus(BaseModel):
    """Video room status."""

    session_id: uuid.UUID = Field(..., description="Session ID")
    participant_count: int = Field(..., description="Number of participants")
    is_active: bool = Field(..., description="Whether the room is active")


@router.get("/turn-credentials", response_model=TurnCredentials)
async def get_turn_credentials(_auth: Auth) -> TurnCredentials:
    """Get TURN server credentials for WebRTC.

    Returns ICE server configuration including STUN and TURN servers.
    """
    settings = get_settings()

    ice_servers: list[dict[str, Any]] = [
        # Free STUN servers
        {"urls": "stun:stun.metered.ca:80"},
        {"urls": "stun:stun.l.google.com:19302"},
    ]

    # Add TURN servers if configured
    if settings.turn_enabled and settings.metered_turn_username:
        ice_servers.extend(
            [
                {
                    "urls": "turn:global.relay.metered.ca:80",
                    "username": settings.metered_turn_username,
                    "credential": settings.metered_turn_credential,
                },
                {
                    "urls": "turn:global.relay.metered.ca:80?transport=tcp",
                    "username": settings.metered_turn_username,
                    "credential": settings.metered_turn_credential,
                },
                {
                    "urls": "turn:global.relay.metered.ca:443",
                    "username": settings.metered_turn_username,
                    "credential": settings.metered_turn_credential,
                },
                {
                    "urls": "turns:global.relay.metered.ca:443?transport=tcp",
                    "username": settings.metered_turn_username,
                    "credential": settings.metered_turn_credential,
                },
            ]
        )

    return TurnCredentials(ice_servers=ice_servers)


@router.get("/rooms/{session_id}/status", response_model=RoomStatus)
async def get_room_status(
    auth: Auth,
    session: DbSession,
    session_id: uuid.UUID,
) -> RoomStatus:
    """Get the status of a video room."""
    # Verify session belongs to org
    result = await session.execute(
        select(Session)
        .join(Session.patient)
        .where(
            Session.id == session_id,
            Session.patient.has(organization_id=auth.organization_id),
        )
    )
    db_session = result.scalar_one_or_none()
    if not db_session:
        raise NotFoundError("Session not found")

    room_service = get_video_room_service()
    count = await room_service.get_participant_count(session_id)

    return RoomStatus(
        session_id=session_id,
        participant_count=count,
        is_active=count > 0,
    )


@router.websocket("/sessions/{session_id}/signal")
async def video_signaling(
    websocket: WebSocket,
    session_id: uuid.UUID,
    api_key: str = Query(..., alias="api_key"),
    participant_id: str = Query(...),
) -> None:
    """WebSocket endpoint for WebRTC signaling.

    Handles SDP offer/answer exchange and ICE candidate relay.

    Query params:
        api_key: API key for authentication
        participant_id: Unique identifier for this participant (e.g., user ID)

    Message types (JSON):
        - {"type": "offer", "sdp": "..."} - SDP offer from caller
        - {"type": "answer", "sdp": "..."} - SDP answer from callee
        - {"type": "ice", "candidate": {...}} - ICE candidate
        - {"type": "join"} - Announce joining the room
        - {"type": "leave"} - Announce leaving the room
    """
    # Validate API key
    if not is_valid_api_key_format(api_key):
        await websocket.close(code=4001, reason="Invalid API key format")
        return

    # Get database session for auth
    async for db_session in get_db_session():
        # Find matching API key
        api_key_result = await db_session.execute(
            select(ApiKey).where(ApiKey.is_active == True)  # noqa: E712
        )
        active_keys = api_key_result.scalars().all()

        org_id: uuid.UUID | None = None
        for key in active_keys:
            if verify_api_key(api_key, key.key_hash):
                org_id = key.organization_id
                break

        if not org_id:
            await websocket.close(code=4001, reason="Invalid API key")
            return

        # Verify session exists and belongs to org
        session_result = await db_session.execute(
            select(Session)
            .join(Session.patient)
            .where(
                Session.id == session_id,
                Session.patient.has(organization_id=org_id),
            )
        )
        db_session_obj = session_result.scalar_one_or_none()
        if not db_session_obj:
            await websocket.close(code=4004, reason="Session not found")
            return

        # Check if video chat is enabled for the org
        org_result = await db_session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one()
        if not org.video_chat_enabled:
            await websocket.close(code=4003, reason="Video chat not enabled")
            return

        break

    # Accept WebSocket connection
    await websocket.accept()

    room_service = get_video_room_service()

    try:
        # Join the room
        await room_service.join(session_id, participant_id, websocket)

        # Notify others that someone joined
        await room_service.broadcast(
            session_id,
            {"type": "peer_joined", "participant_id": participant_id},
            exclude_participant=participant_id,
        )

        # Handle messages
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type in ("offer", "answer", "ice"):
                # Relay signaling messages to other participants
                await room_service.broadcast(
                    session_id,
                    {**data, "from": participant_id},
                    exclude_participant=participant_id,
                )
            elif msg_type == "leave":
                break
            # Ignore unknown message types

    except WebSocketDisconnect:
        pass
    finally:
        # Leave the room
        await room_service.leave(session_id, participant_id)

        # Notify others
        await room_service.broadcast(
            session_id,
            {"type": "peer_left", "participant_id": participant_id},
        )
