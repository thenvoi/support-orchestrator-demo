"""
WebSocket bridge that observes Thenvoi room activity and forwards events
to the UI dashboard.

Architecture:
    Thenvoi WS (rooms) ---> EventBridge ---> UI clients (ws://localhost:8765)

The bridge:
1. Registers a temporary "UIObserver" agent via the Thenvoi REST API.
2. Joins all 5 support-orchestrator rooms as a silent observer.
3. Listens for WebSocket messages in all rooms via the Thenvoi platform WS.
4. Parses orchestrator/v1 protocol messages and detects agent status changes.
5. Forwards structured JSON events to all connected UI dashboard clients.

If the Thenvoi connection fails (missing API key, server down), the bridge
falls back to "demo mode" that generates simulated events matching the
sarah@acme.com demo scenario at realistic timing intervals when a UI client
connects and sends {"action": "start_demo"}.

Run from the project root:
    python ui/bridge/event_bridge.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import websockets
from websockets.server import serve

from thenvoi.client.streaming.client import WebSocketClient

# ---------------------------------------------------------------------------
# Resolve project root and load .env
# ---------------------------------------------------------------------------

# When run as `python ui/bridge/event_bridge.py` from project root, __file__
# is ui/bridge/event_bridge.py.  We walk up to the project root to find .env.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))

# Add src/ to path so imports of thenvoi_integration work if needed
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

from dotenv import load_dotenv

_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
if os.path.exists(_ENV_PATH):
    load_dotenv(_ENV_PATH)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("event_bridge")
logger.setLevel(logging.DEBUG)

# Enable DEBUG for Phoenix Channels to trace WS frame delivery
logging.getLogger("phoenix_channels_python_client").setLevel(logging.DEBUG)
logging.getLogger("thenvoi.client.streaming").setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOCAL_WS_PORT = int(os.environ.get("BRIDGE_WS_PORT", "8765"))

# Thenvoi platform
THENVOI_REST_URL = os.environ.get("THENVOI_REST_URL", "").rstrip("/")
THENVOI_WS_URL = os.environ.get("THENVOI_WS_URL", "")
THENVOI_API_KEY = os.environ.get("THENVOI_USER_API_KEY", "") or os.environ.get("THENVOI_API_KEY", "")

# Room IDs from .env (populated by setup_demo.py)
ROOM_IDS: dict[str, str] = {}
_ROOM_ENV_MAP = {
    "user": "SUPPORT_USER_ROOM_ID",
    "excel": "SUPPORT_EXCEL_ROOM_ID",
    "github": "SUPPORT_GITHUB_ROOM_ID",
    "browser": "SUPPORT_BROWSER_ROOM_ID",
    "linear": "SUPPORT_LINEAR_ROOM_ID",
}

for label, env_var in _ROOM_ENV_MAP.items():
    val = os.environ.get(env_var, "")
    if val:
        ROOM_IDS[label] = val

# Reverse mapping: room_id -> human label
_ROOM_LABELS: dict[str, str] = {v: k for k, v in ROOM_IDS.items()}

# Friendly room names used in forwarded events (match the R-xxx convention)
_ROOM_DISPLAY_NAMES: dict[str, str] = {
    "user": "R-user-support",
    "excel": "R-excel",
    "github": "R-github-support",
    "browser": "R-browser",
    "linear": "R-linear",
}

# Agent name -> UI key mapping (used for status events)
_AGENT_NAME_TO_UI_KEY: dict[str, str] = {
    "SupportOrchestrator": "orchestrator",
    "ExcelAgent": "excel",
    "GitHubSupportAgent": "github",
    "BrowserAgent": "browser",
    "LinearAgent": "linear",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _make_event(event_type: str, **kwargs: Any) -> dict:
    """Build a bridge event dict with a timestamp."""
    return {"type": event_type, "timestamp": _now_iso(), **kwargs}


# ---------------------------------------------------------------------------
# Thenvoi observer agent lifecycle
# ---------------------------------------------------------------------------

class ThenvoidObserver:
    """
    Manages a temporary UIObserver agent on the Thenvoi platform.

    Lifecycle:
        1. register()   -- create the agent, obtain agent_id + agent_api_key
        2. join_rooms()  -- add the observer as a participant in every room
        3. cleanup()     -- delete the agent (best-effort)
    """

    def __init__(self, rest_url: str, user_api_key: str) -> None:
        self.rest_url = rest_url
        self.user_api_key = user_api_key
        self.agent_id: str | None = None
        self.agent_api_key: str | None = None
        self._client = httpx.AsyncClient(
            base_url=self.rest_url,
            headers={
                "X-API-Key": self.user_api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def register(self) -> None:
        """Register a temporary UIObserver agent.

        If a stale UIObserver already exists (422 on register), delete it first
        and retry.
        """
        payload = {
            "agent": {
                "name": "UIObserver",
                "description": "Temporary observer for the UI dashboard bridge.",
            }
        }
        resp = await self._client.post("/api/v1/me/agents/register", json=payload)
        if resp.status_code == 422:
            # Stale UIObserver exists — find and delete it, then retry
            logger.warning("UIObserver already exists. Cleaning up stale agent...")
            await self._cleanup_stale_observers()
            resp = await self._client.post("/api/v1/me/agents/register", json=payload)
        resp.raise_for_status()
        data = resp.json().get("data", resp.json())
        self.agent_id = data.get("agent", {}).get("id")
        self.agent_api_key = data.get("credentials", {}).get("api_key")
        logger.info(
            "UIObserver registered: agent_id=%s, key=%s...",
            self.agent_id,
            (self.agent_api_key or "")[:20],
        )

    async def _cleanup_stale_observers(self) -> None:
        """Delete any existing UIObserver agents to allow fresh registration."""
        try:
            resp = await self._client.get("/api/v1/me/agents")
            if resp.status_code == 200:
                agents = resp.json().get("data", [])
                for agent in agents:
                    if agent.get("name") == "UIObserver":
                        agent_id = agent.get("id")
                        logger.info("Deleting stale UIObserver: %s", agent_id)
                        await self._client.delete(
                            f"/api/v1/me/agents/{agent_id}",
                            params={"force": "true"},
                        )
        except Exception as exc:
            logger.warning("Failed to clean up stale observers: %s", exc)

    async def join_rooms(self, room_ids: dict[str, str]) -> None:
        """Add the observer agent to every room as a member."""
        if not self.agent_id:
            raise RuntimeError("Observer agent not registered yet.")
        for label, room_id in room_ids.items():
            try:
                payload = {
                    "participant": {
                        "participant_id": self.agent_id,
                        "role": "member",
                    }
                }
                resp = await self._client.post(
                    f"/api/v1/me/chats/{room_id}/participants",
                    json=payload,
                )
                resp.raise_for_status()
                logger.info("UIObserver joined room %s (%s)", label, room_id)
            except httpx.HTTPStatusError as exc:
                # 422 often means already a participant -- tolerate it
                if exc.response.status_code == 422:
                    logger.warning(
                        "UIObserver may already be in room %s (%s): %s",
                        label,
                        room_id,
                        exc.response.text,
                    )
                else:
                    raise

    async def cleanup(self) -> None:
        """Delete the observer agent (best-effort)."""
        if not self.agent_id:
            return
        try:
            resp = await self._client.delete(
                f"/api/v1/me/agents/{self.agent_id}",
                params={"force": "true"},
            )
            resp.raise_for_status()
            logger.info("UIObserver agent deleted: %s", self.agent_id)
        except Exception as exc:
            logger.warning("Failed to delete UIObserver agent: %s", exc)
        finally:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# Thenvoi WebSocket listener
# ---------------------------------------------------------------------------

class ThenvoidWsListener:
    """
    Connects to the Thenvoi platform WebSocket as the UIObserver agent and
    listens for messages across all joined rooms.

    Uses the Thenvoi SDK's WebSocketClient (Phoenix Channels v2 protocol)
    for correct topic subscription and event handling.

    Parsed events are pushed into an asyncio.Queue for the local WS server
    to forward to UI clients.
    """

    def __init__(
        self,
        ws_url: str,
        api_key: str,
        event_queue: asyncio.Queue,
        agent_id: str | None = None,
    ) -> None:
        self.ws_url = ws_url
        self.api_key = api_key
        self.agent_id = agent_id
        self.event_queue = event_queue
        self._running = False
        self._ws_client: WebSocketClient | None = None

    async def run(self) -> None:
        """Connect and listen using the Thenvoi SDK WebSocketClient."""
        self._running = True
        backoff = 1.0

        while self._running:
            try:
                await self._listen_once()
            except Exception as exc:
                if not self._running:
                    break
                logger.warning(
                    "Thenvoi WS connection lost (%s). Reconnecting in %.0fs...",
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)

    async def _listen_once(self) -> None:
        """Single connection session using the SDK WebSocketClient."""
        logger.info("Connecting to Thenvoi WS: %s", self.ws_url.split("?")[0])

        self._ws_client = WebSocketClient(
            ws_url=self.ws_url,
            api_key=self.api_key,
            agent_id=self.agent_id,
        )

        async with self._ws_client as ws:
            logger.info("Thenvoi WS connected (Phoenix Channels v2).")
            await self.event_queue.put(
                _make_event("bridge_status", status="connected")
            )

            # Subscribe to chat_room channels for each room.
            # join_chat_room_channel handles message_created events natively.
            # We additionally register a per-event handler for message_updated
            # because agent responses (via thenvoi_send_message) arrive as
            # message_updated events, not message_created.
            for label, room_id in ROOM_IDS.items():
                handler = self._make_message_handler(room_id)

                # Standard SDK subscription for message_created
                await ws.join_chat_room_channel(room_id, handler)
                logger.info("Subscribed to chat_room:%s (%s) [message_created]", room_id, label)

                # Add per-event handler for message_updated on the same topic.
                # The PHXChannelsClient calls per-event handlers alongside the
                # async_callback, so message_updated events will be processed
                # even though _handle_events warns about them (harmless).
                async def _on_message_updated(payload_dict: dict, h=handler, _label=label) -> None:
                    from thenvoi.client.streaming.client import MessageCreatedPayload
                    logger.debug(
                        "RAW message_updated in %s: keys=%s sender=%s content_preview=%s",
                        _label,
                        list(payload_dict.keys()) if isinstance(payload_dict, dict) else type(payload_dict).__name__,
                        payload_dict.get("sender_name", "?") if isinstance(payload_dict, dict) else "?",
                        (str(payload_dict.get("content", ""))[:120]) if isinstance(payload_dict, dict) else "?",
                    )
                    try:
                        parsed = MessageCreatedPayload(**payload_dict)
                    except Exception:
                        parsed = payload_dict
                    await h(parsed)

                topic = f"chat_room:{room_id}"
                ws.client.add_event_handler(topic, "message_updated", _on_message_updated)
                logger.info("Added message_updated handler for %s (%s)", room_id, label)

            # Run the WebSocket event loop (blocks until disconnect)
            await ws.run_forever()

    def _make_message_handler(self, room_id: str):
        """Create an async callback for message_created events in a room."""
        room_label = _ROOM_LABELS.get(room_id, room_id)
        async def _on_message_created(payload) -> None:
            logger.info("WS event received in room %s (%s): %s", room_label, room_id[:8], type(payload).__name__)
            await self._process_message(room_id, payload)
        return _on_message_created

    async def _process_message(self, room_id: str, payload) -> None:
        """Process a message_created event from a Thenvoi room."""
        # payload is a MessageCreatedPayload pydantic model
        sender_name = getattr(payload, "sender_name", None) or "unknown"
        content = getattr(payload, "content", "") or ""
        message_id = getattr(payload, "id", str(uuid.uuid4()))
        message_type = getattr(payload, "message_type", "text")

        room_label = _ROOM_LABELS.get(room_id, room_id)
        room_display = _ROOM_DISPLAY_NAMES.get(room_label, room_label)

        logger.debug(
            "Processing msg in %s: sender=%s type=%s id=%s content_len=%d content_preview=%s",
            room_label, sender_name, message_type, str(message_id)[:8],
            len(content), content[:100] if content else "(empty)",
        )

        # Skip messages from our own observer
        if sender_name == "UIObserver":
            return

        # Skip non-text messages (events, typing indicators, etc.)
        if message_type not in ("text", ""):
            logger.debug(
                "Skipping non-text message (type=%s) from %s in %s",
                message_type, sender_name, room_label,
            )
            return

        logger.info(
            "Room %s [%s]: %s says: %s",
            room_label, room_id[:8], sender_name, content[:80],
        )

        # Forward the raw message event
        await self.event_queue.put(
            _make_event(
                "message",
                room=room_display,
                room_id=room_id,
                sender=sender_name,
                content=content,
                message_id=message_id,
            )
        )

        # Try to parse orchestrator/v1 protocol JSON from the content
        is_protocol = await self._try_parse_protocol(content, sender_name, room_display)

        # Note: orchestrator completion is handled by the UI's idle timer,
        # since we can't reliably distinguish the initial ack from the final
        # response (both are plain text in the user room).

    async def _try_parse_protocol(
        self, content: str, sender: str, room: str
    ) -> bool:
        """Attempt to extract orchestrator/v1 protocol data from message content.

        Returns True if protocol JSON was found and processed.
        """
        # The content may contain a mention prefix like "@ExcelAgent {...}"
        # Strip the mention prefix to get at the JSON.
        json_str = content.strip()

        # Remove leading @mention if present
        if json_str.startswith("@"):
            # Find the first { which starts the JSON
            brace_idx = json_str.find("{")
            if brace_idx > 0:
                json_str = json_str[brace_idx:]

        try:
            proto = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            return False

        if not isinstance(proto, dict) or proto.get("protocol") != "orchestrator/v1":
            return False

        msg_type = proto.get("type", "")
        ui_key = _AGENT_NAME_TO_UI_KEY.get(sender, sender)

        if msg_type == "task_request":
            intent = proto.get("intent", "")
            task_id = proto.get("task_id", "")
            await self.event_queue.put(
                _make_event(
                    "agent_status",
                    agent=ui_key,
                    status="working",
                    task=intent,
                    task_id=task_id,
                    room=room,
                )
            )

        elif msg_type == "task_result":
            status = proto.get("status", "")
            task_id = proto.get("task_id", "")
            processing_ms = proto.get("processing_ms", 0)
            agent_status = "done" if status == "success" else "error"
            await self.event_queue.put(
                _make_event(
                    "agent_status",
                    agent=ui_key,
                    status=agent_status,
                    task=f"task_result ({status})",
                    task_id=task_id,
                    processing_ms=processing_ms,
                    room=room,
                )
            )

        return True

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# Demo mode scenario generator
# ---------------------------------------------------------------------------

# These events mirror CONFIG.DEMO_SCENARIOS.branchA from config.js, matching
# the sarah@acme.com known-bug scenario with realistic timing intervals.

_DEMO_EVENTS: list[dict] = [
    # t=0ms -- Customer sends initial message
    {
        "t": 0,
        "type": "user_message",
        "from": "user",
        "to": "orchestrator",
        "payload": {
            "text": (
                "Hi, I'm sarah@acme.com. The dashboard export to PDF has been "
                "broken since last Tuesday. It just spins forever and never "
                "downloads. This is blocking our weekly reporting. Can you help?"
            ),
        },
    },
    # t=500ms -- Orchestrator acknowledges receipt
    {
        "t": 500,
        "type": "agent_status",
        "agent": "orchestrator",
        "status": "thinking",
        "payload": {
            "text": (
                "Received support request from sarah@acme.com. Analyzing the "
                "issue and determining which specialist agents to engage..."
            ),
        },
    },
    # t=1000ms -- Orchestrator dispatches 3 parallel tasks
    {
        "t": 1000,
        "type": "dispatch",
        "from": "orchestrator",
        "targets": ["excel", "github", "browser"],
        "payload": {
            "text": "Dispatching parallel investigation to 3 specialist agents.",
            "tasks": {
                "excel": (
                    "Look up customer sarah@acme.com -- retrieve account tier, "
                    "contract status, and any prior support tickets."
                ),
                "github": (
                    'Search for issues related to "dashboard PDF export" or '
                    '"PDF download spinning". Check for recent PRs or fixes.'
                ),
                "browser": (
                    "Search the product knowledge base and release notes for "
                    "any known issues or workarounds related to PDF export."
                ),
            },
        },
    },
    # t=1200ms -- Excel agent starts working
    {
        "t": 1200,
        "type": "agent_status",
        "agent": "excel",
        "status": "working",
        "payload": {
            "text": "Querying CRM for customer record: sarah@acme.com...",
        },
    },
    # t=1300ms -- GitHub agent starts working
    {
        "t": 1300,
        "type": "agent_status",
        "agent": "github",
        "status": "working",
        "payload": {
            "text": 'Searching repositories for "dashboard PDF export" issues...',
        },
    },
    # t=1400ms -- Browser agent starts working
    {
        "t": 1400,
        "type": "agent_status",
        "agent": "browser",
        "status": "working",
        "payload": {
            "text": (
                "Navigating to knowledge base, searching for PDF export articles..."
            ),
        },
    },
    # t=3000ms -- Excel agent completes
    {
        "t": 3000,
        "type": "agent_result",
        "agent": "excel",
        "status": "done",
        "payload": {
            "text": (
                "Customer found: Sarah Chen, Acme Corp. Enterprise plan, "
                "contract active through 2026-12. Previous ticket #4521 "
                "(resolved) about slow exports in Jan 2025. Account in good "
                "standing, high-priority support tier."
            ),
        },
    },
    # t=5000ms -- GitHub agent completes
    {
        "t": 5000,
        "type": "agent_result",
        "agent": "github",
        "status": "done",
        "payload": {
            "text": (
                'Found issue #1847: "PDF export hangs indefinitely on large '
                "dashboards\" opened 6 days ago. Labeled as bug, priority P1. "
                "Root cause identified -- timeout regression in pdf-renderer "
                "v3.2.1. Fix merged in PR #1853 but not yet deployed. Hotfix "
                "branch: fix/pdf-export-timeout."
            ),
        },
    },
    # t=8000ms -- Browser agent completes
    {
        "t": 8000,
        "type": "agent_result",
        "agent": "browser",
        "status": "done",
        "payload": {
            "text": (
                "Knowledge base article KB-2094 confirms known issue with PDF "
                "exports since v3.2.1 (released last Tuesday). Workaround "
                'available: append "?legacy_render=true" to the dashboard URL '
                "before exporting. Fix ETA: next patch release scheduled for "
                "Wednesday."
            ),
        },
    },
    # t=8500ms -- Orchestrator synthesizes results
    {
        "t": 8500,
        "type": "agent_status",
        "agent": "orchestrator",
        "status": "thinking",
        "payload": {
            "text": (
                "All 3 agents reported back. Synthesizing findings into a "
                "unified response for the customer..."
            ),
        },
    },
    # t=10000ms -- Orchestrator sends final response
    {
        "t": 10000,
        "type": "final_response",
        "from": "orchestrator",
        "to": "user",
        "payload": {
            "text": (
                "Hi Sarah! I've investigated your PDF export issue across our "
                "systems. Here's what I found:\n\n"
                "**Root Cause:** A timeout regression was introduced in our "
                "v3.2.1 release last Tuesday (tracked as issue #1847, P1 "
                "priority). This affects PDF exports on larger dashboards.\n\n"
                "**Immediate Workaround:** Add `?legacy_render=true` to your "
                "dashboard URL before exporting. This bypasses the new renderer "
                "and should let you complete your weekly reports right away.\n\n"
                "**Permanent Fix:** The fix has already been merged (PR #1853) "
                "and is scheduled for deployment in Wednesday's patch release.\n\n"
                "As an Enterprise customer, I've flagged your account for "
                "priority notification when the patch goes live. Is there "
                "anything else I can help with?"
            ),
        },
    },
]


class DemoRunner:
    """
    Plays back the sarah@acme.com Branch A scenario by pushing events into
    the event queue at realistic timing intervals.
    """

    def __init__(self, event_queue: asyncio.Queue) -> None:
        self.event_queue = event_queue
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        """Schedule all demo events with their timing offsets."""
        if self._running:
            logger.warning("Demo is already running; ignoring duplicate start.")
            return

        self._running = True
        logger.info("Demo mode: starting sarah@acme.com scenario playback.")

        await self.event_queue.put(
            _make_event("bridge_status", status="demo")
        )
        await self.event_queue.put(
            _make_event("demo_started", scenario="branchA")
        )

        for evt in _DEMO_EVENTS:
            task = asyncio.create_task(self._schedule_event(evt))
            self._tasks.append(task)

        # Schedule demo completion
        last_t = _DEMO_EVENTS[-1]["t"]
        task = asyncio.create_task(self._schedule_completion(last_t + 1500))
        self._tasks.append(task)

    async def _schedule_event(self, evt: dict) -> None:
        """Wait for the event's offset, then push it to the queue."""
        delay_s = evt["t"] / 1000.0
        await asyncio.sleep(delay_s)
        if not self._running:
            return

        # Build a bridge event that matches what the UI DemoRunner expects
        bridge_evt = dict(evt)
        bridge_evt["timestamp"] = _now_iso()
        await self.event_queue.put(bridge_evt)

    async def _schedule_completion(self, delay_ms: int) -> None:
        """Signal demo completion."""
        await asyncio.sleep(delay_ms / 1000.0)
        if not self._running:
            return
        await self.event_queue.put(_make_event("demo_complete", scenario="branchA"))
        self._running = False
        logger.info("Demo mode: scenario playback complete.")

    def stop(self) -> None:
        """Cancel all pending demo tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()


# ---------------------------------------------------------------------------
# Local WebSocket server (UI-facing, port 8765)
# ---------------------------------------------------------------------------

class BridgeServer:
    """
    Runs a local WebSocket server that:
    - Accepts UI dashboard connections on ws://localhost:8765
    - Drains the event_queue and broadcasts events to all connected clients
    - Accepts commands from UI clients (e.g., {"action": "start_demo"})
    """

    def __init__(
        self,
        event_queue: asyncio.Queue,
        demo_runner: DemoRunner,
        is_live_mode: bool,
        rest_url: str = "",
        user_api_key: str = "",
        agent_api_key: str = "",
    ) -> None:
        self.event_queue = event_queue
        self.demo_runner = demo_runner
        self.is_live_mode = is_live_mode
        self.rest_url = rest_url
        self.user_api_key = user_api_key
        self.agent_api_key = agent_api_key
        self._clients: set[websockets.WebSocketServerProtocol] = set()
        self._broadcast_task: asyncio.Task | None = None

    async def handler(
        self, websocket: websockets.WebSocketServerProtocol
    ) -> None:
        """Handle a single UI client connection."""
        self._clients.add(websocket)
        client_id = id(websocket)
        logger.info("UI client connected (id=%d, total=%d)", client_id, len(self._clients))

        # Send current mode on connect
        mode = "live" if self.is_live_mode else "demo_available"
        try:
            await websocket.send(
                json.dumps(
                    _make_event(
                        "bridge_status",
                        status=mode,
                        rooms=list(ROOM_IDS.keys()) if self.is_live_mode else [],
                    )
                )
            )
        except websockets.exceptions.ConnectionClosed:
            self._clients.discard(websocket)
            return

        try:
            async for raw_msg in websocket:
                await self._handle_client_message(raw_msg, websocket)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info(
                "UI client disconnected (id=%d, total=%d)",
                client_id,
                len(self._clients),
            )

    async def _handle_client_message(
        self,
        raw_msg: str,
        websocket: websockets.WebSocketServerProtocol,
    ) -> None:
        """Process an incoming message from a UI client."""
        try:
            data = json.loads(raw_msg)
        except (json.JSONDecodeError, TypeError):
            return

        action = data.get("action", "")

        if action == "start_demo":
            if self.is_live_mode:
                await websocket.send(
                    json.dumps(
                        _make_event(
                            "error",
                            message="Bridge is in live mode; demo not available.",
                        )
                    )
                )
                return
            await self.demo_runner.start()

        elif action == "stop_demo":
            self.demo_runner.stop()
            await self.event_queue.put(
                _make_event("demo_stopped", scenario="branchA")
            )

        elif action == "start_live_demo":
            # Works in both live mode and demo mode
            user_room_id = ROOM_IDS.get("user")
            if not user_room_id:
                await websocket.send(
                    json.dumps(
                        _make_event(
                            "error",
                            message="No user room ID configured. Set SUPPORT_USER_ROOM_ID in .env.",
                        )
                    )
                )
                return

            # Look up orchestrator agent ID from room participants or config
            orchestrator_id = os.environ.get("SUPPORT_ORCHESTRATOR_AGENT_ID", "")
            if not orchestrator_id:
                # Try to read from agent_config.yaml
                import yaml

                config_path = os.path.join(_PROJECT_ROOT, "src", "config", "agent_config.yaml")
                try:
                    with open(config_path) as f:
                        agent_cfg = yaml.safe_load(f)
                    orchestrator_id = (
                        agent_cfg.get("agents", {})
                        .get("support_orchestrator", {})
                        .get("agent_id", "")
                    )
                except Exception:
                    pass

            # Use a unique timestamp to ensure each demo run looks like a fresh request
            import random
            ts = int(time.time())
            demo_scenarios = [
                (
                    f"@SupportOrchestrator Hi, I'm sarah@acme.com. The dashboard "
                    f"export to PDF has been broken since last Tuesday. It just "
                    f"spins forever and never downloads. This is blocking our "
                    f"weekly reporting. Can you help? [ref:{ts}]"
                ),
                (
                    f"@SupportOrchestrator Hello, this is mike@widgets.io. "
                    f"The CSV export feature on the analytics dashboard throws "
                    f"a 500 error when I try to export more than 1000 rows. "
                    f"Started happening yesterday. Urgent — need this for a "
                    f"board meeting tomorrow. [ref:{ts}]"
                ),
                (
                    f"@SupportOrchestrator Hi, alex@startup.co here. "
                    f"The real-time notifications stopped working about 2 hours "
                    f"ago. I'm not getting any alerts when new orders come in, "
                    f"which is causing us to miss customer orders. [ref:{ts}]"
                ),
            ]
            demo_message = random.choice(demo_scenarios)

            mentions = []
            if orchestrator_id:
                mentions.append({
                    "id": orchestrator_id,
                    "name": "SupportOrchestrator",
                    "handle": "SupportOrchestrator",
                })

            success = await self._post_message_to_room(
                user_room_id, demo_message, mentions=mentions,
            )
            if success:
                await self.event_queue.put(
                    _make_event("bridge_status", status="live_demo_started")
                )
            else:
                await websocket.send(
                    json.dumps(
                        _make_event(
                            "error",
                            message="Failed to post demo message to the user room.",
                        )
                    )
                )

        elif action == "ping":
            try:
                await websocket.send(json.dumps(_make_event("pong")))
            except websockets.exceptions.ConnectionClosed:
                pass

    async def _post_message_to_room(
        self, room_id: str, content: str, mentions: list[dict] | None = None,
    ) -> bool:
        """Post a message to a Thenvoi room via the REST API.

        Uses the UIObserver's agent API key and the agent endpoint so the
        message is sent as the observer agent (not the user).

        Args:
            room_id: The Thenvoi chat room ID.
            content: The message content string.
            mentions: List of mention dicts with 'id', 'name', 'handle' keys.
                      Required by the Thenvoi API for routing.

        Returns:
            True on success, False on failure.
        """
        # Always post as the user (simulating a customer) using the /me endpoint.
        # The agent endpoint requires Authorization: Bearer header, and the demo
        # message should appear as a user message anyway.
        api_key = self.user_api_key
        url = f"{self.rest_url}/api/v1/me/chats/{room_id}/messages"
        headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        msg_payload: dict = {"content": content}
        if mentions:
            msg_payload["mentions"] = mentions
        body = {"message": msg_payload}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
            logger.info(
                "Posted message to room %s (status=%d)", room_id, resp.status_code
            )
            return True
        except Exception as exc:
            logger.error("Failed to post message to room %s: %s", room_id, exc)
            return False

    async def broadcast_loop(self) -> None:
        """Continuously drain the event queue and send to all UI clients."""
        while True:
            event = await self.event_queue.get()
            if not self._clients:
                continue
            payload = json.dumps(event)
            # Broadcast to all connected clients, removing dead ones
            dead: list[websockets.WebSocketServerProtocol] = []
            for ws in self._clients:
                try:
                    await ws.send(payload)
                except websockets.exceptions.ConnectionClosed:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    async def start(self) -> None:
        """Start the local WS server and broadcast loop."""
        self._broadcast_task = asyncio.create_task(self.broadcast_loop())
        async with serve(self.handler, "0.0.0.0", LOCAL_WS_PORT):
            logger.info(
                "Bridge WS server listening on ws://0.0.0.0:%d", LOCAL_WS_PORT
            )
            await asyncio.Future()  # run forever


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def _try_live_mode(event_queue: asyncio.Queue) -> ThenvoidWsListener | None:
    """
    Attempt to set up live Thenvoi observation.

    Returns a ThenvoidWsListener if successful, or None if live mode is
    not possible (missing config, server unreachable, etc.).
    """
    if not THENVOI_REST_URL or not THENVOI_API_KEY or not THENVOI_WS_URL:
        logger.warning(
            "Live mode unavailable: missing THENVOI_REST_URL, THENVOI_API_KEY, "
            "or THENVOI_WS_URL in environment."
        )
        return None

    if not ROOM_IDS:
        logger.warning(
            "Live mode unavailable: no SUPPORT_*_ROOM_ID variables found. "
            "Run setup_demo.py first."
        )
        return None

    observer = ThenvoidObserver(THENVOI_REST_URL, THENVOI_API_KEY)
    try:
        await observer.register()
        await observer.join_rooms(ROOM_IDS)
    except Exception as exc:
        logger.warning("Live mode setup failed: %s", exc)
        try:
            await observer.cleanup()
        except Exception:
            pass
        return None

    if not observer.agent_id or not observer.agent_api_key:
        logger.warning("Live mode setup failed: observer credentials incomplete.")
        try:
            await observer.cleanup()
        except Exception:
            pass
        return None

    # Connect WS as the USER (not the UIObserver agent) so we receive ALL
    # message_created events in every room, not just messages that mention
    # the observer.  The UIObserver is still used to join rooms + post.
    listener = ThenvoidWsListener(
        ws_url=THENVOI_WS_URL,
        api_key=THENVOI_API_KEY,        # user API key -> sees all messages
        event_queue=event_queue,
        agent_id=None,                   # no agent_id -> connect as user
    )
    listener.agent_api_key = observer.agent_api_key  # keep for posting

    return listener


async def main() -> None:
    """
    Bridge entry point.

    1. Try to connect to Thenvoi in live mode.
    2. If that fails, fall back to demo mode.
    3. Start the local WS server for UI clients.
    """
    logger.info("=" * 60)
    logger.info("  Support Orchestrator -- Event Bridge")
    logger.info("=" * 60)
    logger.info("Project root: %s", _PROJECT_ROOT)
    logger.info("Rooms loaded: %s", list(ROOM_IDS.keys()) if ROOM_IDS else "(none)")

    event_queue: asyncio.Queue = asyncio.Queue()

    # --- Attempt live mode ---------------------------------------------------
    listener = await _try_live_mode(event_queue)
    is_live = listener is not None

    if is_live:
        logger.info("Mode: LIVE (observing Thenvoi rooms in real time)")
    else:
        logger.info(
            "Mode: DEMO (Thenvoi connection unavailable; UI clients can "
            'send {"action": "start_demo"} to play the demo scenario)'
        )

    # --- Set up demo runner (always available in demo mode) ------------------
    demo_runner = DemoRunner(event_queue)

    # --- Start local WS server -----------------------------------------------
    # In live mode, pass the UIObserver's agent API key so the bridge can
    # post messages to rooms as the observer agent.
    observer_agent_key = ""
    if is_live and listener:
        observer_agent_key = listener.agent_api_key or ""

    server = BridgeServer(
        event_queue=event_queue,
        demo_runner=demo_runner,
        is_live_mode=is_live,
        rest_url=THENVOI_REST_URL,
        user_api_key=THENVOI_API_KEY,
        agent_api_key=observer_agent_key,
    )

    tasks: list[asyncio.Task] = []

    # Thenvoi WS listener task (live mode only)
    if is_live and listener:
        tasks.append(asyncio.create_task(listener.run()))

    # Local WS server task
    tasks.append(asyncio.create_task(server.start()))

    logger.info("Bridge is running. Press Ctrl+C to stop.")

    # --- Graceful shutdown via signal ----------------------------------------
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received.")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows does not support add_signal_handler
            pass

    try:
        # Wait until shutdown or until a task raises
        done, pending = await asyncio.wait(
            tasks + [asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # If shutdown_event was set, cancel remaining tasks
        for task in pending:
            task.cancel()
    except asyncio.CancelledError:
        pass
    finally:
        # Cleanup
        if is_live and listener:
            listener.stop()
        demo_runner.stop()
        logger.info("Bridge stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
