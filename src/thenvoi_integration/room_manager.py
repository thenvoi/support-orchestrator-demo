"""
Async room manager for the Thenvoi platform.

Wraps the Human API chat room endpoints to create rooms, manage
participants, and retrieve messages using httpx.

Usage:
    async with RoomManager(base_url, api_key) as rm:
        room = await rm.create_room(title="R-user-support")
        await rm.add_participant(room["id"], agent_id, role="member")
        messages = await rm.get_messages(room["id"])
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds).
_DEFAULT_TIMEOUT = 30.0


class RoomManager:
    """
    Manage Thenvoi chat rooms via the Human API.

    All operations use the Human API (``/api/v1/me/...``) and therefore
    require a **user** API key (``thnv_u_...``).

    The class implements the async context-manager protocol so the
    underlying ``httpx.AsyncClient`` is properly closed on exit.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        """
        Args:
            base_url: Thenvoi platform base URL (e.g. ``https://app.thenvoi.com``).
            api_key: User API key with ``thnv_u_`` prefix.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=_DEFAULT_TIMEOUT,
        )

    # -- Context manager support -----------------------------------------------

    async def __aenter__(self) -> RoomManager:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # -- Chat rooms ------------------------------------------------------------

    async def create_room(self, title: str | None = None) -> dict:
        """
        Create a new chat room.

        The authenticated user automatically becomes the room owner.

        Note: Thenvoi auto-generates the room title from the first message,
        so ``title`` is not sent in the request body. It is accepted here
        for logging purposes only.

        Args:
            title: Optional human-readable label (used for logging only).

        Returns:
            Room data dict containing at least ``id``.
        """
        payload: dict[str, Any] = {"chat": {}}

        logger.info("Creating room%s", f" ({title})" if title else "")
        response = await self._client.post("/api/v1/me/chats", json=payload)
        response.raise_for_status()

        data = response.json()
        room = data.get("data", data)
        logger.info(
            "Room created: id=%s%s",
            room.get("id", "?"),
            f" title={title}" if title else "",
        )
        return room

    async def add_participant(
        self,
        chat_id: str,
        participant_id: str,
        role: str = "member",
    ) -> dict:
        """
        Add a participant (agent or user) to a chat room.

        Args:
            chat_id: Chat room ID.
            participant_id: Agent or user UUID to add.
            role: Participant role -- ``"owner"``, ``"admin"``, or ``"member"``
                  (default: ``"member"``).

        Returns:
            Participant data dict returned by the API.
        """
        payload = {
            "participant": {
                "participant_id": participant_id,
                "role": role,
            }
        }

        logger.info(
            "Adding participant %s to room %s (role=%s)",
            participant_id,
            chat_id,
            role,
        )
        response = await self._client.post(
            f"/api/v1/me/chats/{chat_id}/participants",
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        result = data.get("data", data)
        logger.info("Participant added: %s -> room %s", participant_id, chat_id)
        return result

    async def list_rooms(self) -> list[dict]:
        """
        List chat rooms the authenticated user participates in.

        Returns:
            List of room dicts.
        """
        response = await self._client.get("/api/v1/me/chats")
        response.raise_for_status()

        data = response.json()
        rooms = data.get("data", data)
        if not isinstance(rooms, list):
            rooms = [rooms] if rooms else []
        logger.info("Listed %d room(s)", len(rooms))
        return rooms

    async def get_messages(
        self,
        chat_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict]:
        """
        Retrieve messages from a chat room.

        Args:
            chat_id: Chat room ID.
            page: Page number (default: 1).
            page_size: Items per page (default: 50, max: 100).

        Returns:
            List of message dicts.
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}

        response = await self._client.get(
            f"/api/v1/me/chats/{chat_id}/messages",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        messages = data.get("data", data)
        if not isinstance(messages, list):
            messages = [messages] if messages else []
        logger.info("Retrieved %d message(s) from room %s", len(messages), chat_id)
        return messages
