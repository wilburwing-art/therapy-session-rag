"""Video room service for WebRTC signaling."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class VideoRoom:
    """Represents an active video call room."""

    session_id: uuid.UUID
    participants: dict[str, WebSocket] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())


class VideoRoomService:
    """Manages video call rooms for WebRTC signaling.

    This is an in-memory implementation suitable for single-instance deployments.
    For multi-instance deployments, use Redis pub/sub instead.
    """

    def __init__(self) -> None:
        self._rooms: dict[uuid.UUID, VideoRoom] = {}
        self._lock = asyncio.Lock()

    async def join(
        self, session_id: uuid.UUID, participant_id: str, websocket: WebSocket
    ) -> VideoRoom:
        """Join a video room, creating it if it doesn't exist."""
        async with self._lock:
            if session_id not in self._rooms:
                self._rooms[session_id] = VideoRoom(session_id=session_id)

            room = self._rooms[session_id]
            room.participants[participant_id] = websocket
            return room

    async def leave(self, session_id: uuid.UUID, participant_id: str) -> bool:
        """Leave a video room. Returns True if room was closed."""
        async with self._lock:
            if session_id not in self._rooms:
                return False

            room = self._rooms[session_id]
            room.participants.pop(participant_id, None)

            # Close room if empty
            if not room.participants:
                del self._rooms[session_id]
                return True
            return False

    async def broadcast(
        self,
        session_id: uuid.UUID,
        message: dict[str, Any],
        exclude_participant: str | None = None,
    ) -> int:
        """Broadcast a message to all participants in a room.

        Returns the number of participants the message was sent to.
        """
        if session_id not in self._rooms:
            return 0

        room = self._rooms[session_id]
        sent_count = 0

        for participant_id, websocket in list(room.participants.items()):
            if participant_id == exclude_participant:
                continue
            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception:
                # Participant disconnected, clean up
                room.participants.pop(participant_id, None)

        return sent_count

    async def get_participant_count(self, session_id: uuid.UUID) -> int:
        """Get the number of participants in a room."""
        if session_id not in self._rooms:
            return 0
        return len(self._rooms[session_id].participants)

    async def room_exists(self, session_id: uuid.UUID) -> bool:
        """Check if a room exists."""
        return session_id in self._rooms


# Global singleton instance
_video_room_service: VideoRoomService | None = None


def get_video_room_service() -> VideoRoomService:
    """Get the global video room service instance."""
    global _video_room_service
    if _video_room_service is None:
        _video_room_service = VideoRoomService()
    return _video_room_service
