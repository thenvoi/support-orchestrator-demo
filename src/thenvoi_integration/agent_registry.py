"""
Async agent registry for the Thenvoi platform.

Wraps the Human API agent management endpoints to register, list,
and delete agents using httpx.

Usage:
    async with AgentRegistry(base_url, api_key) as registry:
        result = await registry.register_agent("ExcelAgent", "Customer data specialist")
        # IMPORTANT: result["credentials"]["api_key"] is shown ONCE ONLY -- save it!
        agents = await registry.list_agents()
        await registry.delete_agent(agent_id, force=True)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds).
_DEFAULT_TIMEOUT = 30.0


class AgentRegistry:
    """
    Register, list, and delete Thenvoi agents via the Human API.

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

    async def __aenter__(self) -> AgentRegistry:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # -- Agent management ------------------------------------------------------

    async def register_agent(
        self,
        name: str,
        description: str | None = None,
    ) -> dict:
        """
        Register a new external agent with the Thenvoi platform.

        **IMPORTANT**: The response includes a one-time ``api_key`` in
        ``data.credentials.api_key``. This key is shown **only once** and
        must be persisted immediately.

        Args:
            name: Agent display name (e.g. ``"ExcelAgent"``).
            description: Optional agent description.

        Returns:
            Full registration response dict with structure::

                {
                    "data": {
                        "agent": {"id": "...", "name": "...", ...},
                        "credentials": {"api_key": "thnv_a_..."}
                    }
                }
        """
        payload: dict[str, Any] = {
            "agent": {
                "name": name,
            }
        }
        if description:
            payload["agent"]["description"] = description

        logger.info("Registering agent: %s", name)
        response = await self._client.post(
            "/api/v1/me/agents/register",
            json=payload,
        )
        response.raise_for_status()

        data = response.json()
        result = data.get("data", data)

        agent_info = result.get("agent", {})
        agent_id = agent_info.get("id", "?")
        logger.info("Agent registered: %s (id=%s)", name, agent_id)

        # Warn if the key is present -- callers must save it.
        credentials = result.get("credentials", {})
        if credentials.get("api_key"):
            logger.warning(
                "One-time API key returned for %s -- save it immediately! "
                "It will NOT be shown again.",
                name,
            )
        else:
            logger.warning(
                "No API key in response for %s -- check API version compatibility.",
                name,
            )

        return result

    async def list_agents(self) -> list[dict]:
        """
        List agents owned by the authenticated user.

        Returns:
            List of agent dicts.
        """
        response = await self._client.get("/api/v1/me/agents")
        response.raise_for_status()

        data = response.json()
        agents = data.get("data", data)
        if not isinstance(agents, list):
            agents = [agents] if agents else []
        logger.info("Listed %d agent(s)", len(agents))
        return agents

    async def delete_agent(self, agent_id: str, force: bool = False) -> None:
        """
        Delete an agent.

        Args:
            agent_id: Agent ID to delete.
            force: If ``True``, force-delete including all execution history.
                   If ``False`` (default), deletion will fail with 422 if the
                   agent has execution history.
        """
        params: dict[str, Any] = {}
        if force:
            params["force"] = "true"

        logger.info(
            "Deleting agent %s%s", agent_id, " (force)" if force else ""
        )
        response = await self._client.delete(
            f"/api/v1/me/agents/{agent_id}",
            params=params,
        )
        response.raise_for_status()
        logger.info("Agent deleted: %s", agent_id)
