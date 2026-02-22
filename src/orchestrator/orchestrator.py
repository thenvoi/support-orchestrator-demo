"""
Support orchestrator agent for the customer support demo.

Sits at the hub of a hub-and-spoke topology, connecting:
- R-user-support: User <-> SupportOrchestrator room (user-facing conversation)
- R-excel: SupportOrchestrator <-> ExcelAgent room
- R-github-support: SupportOrchestrator <-> GitHubSupportAgent room
- R-browser: SupportOrchestrator <-> BrowserAgent room
- R-linear: SupportOrchestrator <-> LinearAgent room

The orchestrator:
1. Immediately acknowledges user bug reports (target: <1s)
2. Kicks off 3 parallel investigations (Excel, GitHub, Browser)
3. Collects task_result responses from specialists
4. Synthesizes results into an informed support response
5. Conditionally invokes LinearAgent (Branch B: new bug → file ticket)

Uses a custom adapter subclass (OrchestratorAdapter) that extends
ClaudeCodeDesktopAdapter with cross-room messaging support.

Run standalone:
    THENVOI_AGENT_ID=<id> THENVOI_API_KEY=<key> \\
    SUPPORT_USER_ROOM_ID=<room> \\
    SUPPORT_EXCEL_ROOM_ID=<room> \\
    SUPPORT_GITHUB_ROOM_ID=<room> \\
    SUPPORT_BROWSER_ROOM_ID=<room> \\
    SUPPORT_LINEAR_ROOM_ID=<room> \\
    python src/orchestrator/orchestrator.py

Or:
    python -m orchestrator.orchestrator
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from thenvoi import Agent
from thenvoi.adapters import ClaudeCodeDesktopAdapter
from thenvoi.core.protocols import AgentToolsProtocol
from thenvoi.runtime.tools import AgentTools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Room configuration
# ---------------------------------------------------------------------------

class SupportRoomConfig:
    """
    Holds room IDs for the support orchestrator hub-and-spoke topology.

    5 rooms: user, excel, github, browser, linear.
    Room IDs are loaded from environment variables prefixed with SUPPORT_*.
    """

    def __init__(
        self,
        user_room_id: str,
        excel_room_id: str,
        github_room_id: str,
        browser_room_id: str,
        linear_room_id: str,
    ):
        self.user_room_id = user_room_id
        self.excel_room_id = excel_room_id
        self.github_room_id = github_room_id
        self.browser_room_id = browser_room_id
        self.linear_room_id = linear_room_id

    @classmethod
    def from_env(cls) -> SupportRoomConfig:
        """
        Load room configuration from environment variables.

        Required env vars:
            SUPPORT_USER_ROOM_ID
            SUPPORT_EXCEL_ROOM_ID
            SUPPORT_GITHUB_ROOM_ID
            SUPPORT_BROWSER_ROOM_ID
            SUPPORT_LINEAR_ROOM_ID

        Raises:
            ValueError: If any required environment variable is missing.
        """
        env_map = {
            "user": "SUPPORT_USER_ROOM_ID",
            "excel": "SUPPORT_EXCEL_ROOM_ID",
            "github": "SUPPORT_GITHUB_ROOM_ID",
            "browser": "SUPPORT_BROWSER_ROOM_ID",
            "linear": "SUPPORT_LINEAR_ROOM_ID",
        }

        values = {}
        missing = []
        for key, env_var in env_map.items():
            val = os.environ.get(env_var, "")
            if not val:
                missing.append(env_var)
            values[key] = val

        if missing:
            raise ValueError(
                f"Missing required room configuration: {', '.join(missing)}. "
                "Set these environment variables or run setup_demo.py first."
            )

        return cls(
            user_room_id=values["user"],
            excel_room_id=values["excel"],
            github_room_id=values["github"],
            browser_room_id=values["browser"],
            linear_room_id=values["linear"],
        )

    def specialist_room_for(self, specialist: str) -> str | None:
        """
        Get the room ID for a specialist by name (case-insensitive keyword match).

        Args:
            specialist: Specialist name or keyword (e.g., "ExcelAgent", "excel")

        Returns:
            Room ID string, or None if no match.
        """
        name = specialist.lower()
        if "excel" in name:
            return self.excel_room_id
        if "github" in name:
            return self.github_room_id
        if "browser" in name:
            return self.browser_room_id
        if "linear" in name:
            return self.linear_room_id
        return None

    def room_label(self, room_id: str) -> str:
        """
        Get a human-readable label for a room ID.

        Args:
            room_id: Room identifier.

        Returns:
            Label string (e.g., "user-room", "excel-room", or the raw ID).
        """
        if room_id == self.user_room_id:
            return "user-room"
        if room_id == self.excel_room_id:
            return "excel-room"
        if room_id == self.github_room_id:
            return "github-room"
        if room_id == self.browser_room_id:
            return "browser-room"
        if room_id == self.linear_room_id:
            return "linear-room"
        return room_id


# ---------------------------------------------------------------------------
# Custom adapter with cross-room messaging
# ---------------------------------------------------------------------------

class OrchestratorAdapter(ClaudeCodeDesktopAdapter):
    """
    Extended ClaudeCodeDesktopAdapter with cross-room messaging support.

    The base adapter's _execute_action always sends to the room that triggered
    the event (because AgentTools is bound to a room_id). The orchestrator
    needs to send to specialist rooms from the user-room context, so this
    subclass intercepts actions that contain a ``room_id`` field and creates a
    temporary AgentTools bound to the target room for that send.

    All other actions are dispatched through the default path.
    """

    def __init__(
        self,
        room_config: SupportRoomConfig,
        custom_section: str | None = None,
        cli_timeout: int = 30000,
        allowed_tools: list[str] | None = None,
        verbose: bool = False,
    ):
        super().__init__(
            custom_section=custom_section,
            cli_timeout=cli_timeout,
            allowed_tools=allowed_tools or [],
            verbose=verbose,
        )
        self.room_config = room_config

    async def _execute_action(
        self,
        action_data: dict[str, Any],
        tools: AgentToolsProtocol,
    ) -> None:
        """
        Execute a parsed action, with cross-room routing for send_message.

        If the action dict contains a ``room_id`` field that differs from the
        current tool's room, a temporary AgentTools is created to send the
        message to the correct room.

        Args:
            action_data: Action dict from the LLM (must have 'action' key).
            tools: Agent tools bound to the current (source) room.
        """
        action = action_data.get("action")
        target_room_id = action_data.get("room_id")

        # Cross-room send_message: create tools bound to target room
        if (
            action == "send_message"
            and target_room_id
            and isinstance(tools, AgentTools)
            and target_room_id != tools.room_id
        ):
            target_label = self.room_config.room_label(target_room_id)
            content = action_data.get("content", "")
            mentions = action_data.get("mentions", [])

            logger.info(
                f"Cross-room send: {self.room_config.room_label(tools.room_id)} -> "
                f"{target_label}: {content[:60]}{'...' if len(content) > 60 else ''}"
            )

            # Create a temporary AgentTools instance bound to the target room.
            target_tools = AgentTools(
                room_id=target_room_id,
                rest=tools.rest,
                participants=None,
                agent_id=getattr(tools, '_agent_id', None),
            )

            # Load participants for the target room so @mentions resolve
            try:
                target_participants = (
                    await tools.rest.agent_api_participants.list_agent_chat_participants(
                        chat_id=target_room_id,
                    )
                )
                if target_participants.data:
                    target_tools._participants = [
                        {
                            "id": p.id,
                            "name": p.name,
                            "handle": getattr(p, "handle", "") or "",
                            "type": getattr(p, "type", ""),
                        }
                        for p in target_participants.data
                    ]
            except Exception as e:
                logger.warning(
                    f"Failed to load participants for {target_label}: {e}. "
                    "Mention resolution may fail."
                )

            try:
                await target_tools.send_message(content, mentions)
                logger.info(
                    f"Cross-room message sent to {target_label}: "
                    f"{content[:50]}{'...' if len(content) > 50 else ''}"
                )
            except Exception as e:
                logger.error(
                    f"Cross-room send to {target_label} failed: {e}",
                    exc_info=True,
                )
                await tools.send_event(
                    content=f"Failed to send to {target_label}: {self._sanitize_error(str(e))}",
                    message_type="error",
                )
            return

        # Default: delegate to base class for same-room actions
        await super()._execute_action(action_data, tools)


# ---------------------------------------------------------------------------
# Custom section prompt builder
# ---------------------------------------------------------------------------

def build_orchestrator_prompt(room_config: SupportRoomConfig) -> str:
    """
    Build the custom_section prompt for the support orchestrator.

    This prompt encodes the 3-phase customer support workflow:
    1. Acknowledge the bug report immediately
    2. Delegate in parallel to Excel, GitHub, Browser
    3. Synthesize results (Branch A: known bug, Branch B: new bug, Branch C: plan limitation)

    Args:
        room_config: Room configuration with all 5 room IDs.

    Returns:
        Complete custom_section prompt string.
    """
    return f"""You are the **SupportOrchestrator**, a customer support hub agent that investigates bug reports
by coordinating 4 specialist agents in parallel.

## Your Role

You sit in 5 Thenvoi chat rooms simultaneously:
- **User room** (`{room_config.user_room_id}`): Where the customer talks to you.
- **Excel room** (`{room_config.excel_room_id}`): Where you delegate to @ExcelAgent for customer data lookup.
- **GitHub room** (`{room_config.github_room_id}`): Where you delegate to @GitHubSupportAgent for known bug search.
- **Browser room** (`{room_config.browser_room_id}`): Where you delegate to @BrowserAgent for issue reproduction.
- **Linear room** (`{room_config.linear_room_id}`): Where you delegate to @LinearAgent for filing new bug tickets.

Your primary job: receive a customer's bug report, kick off parallel investigations, synthesize the
results, and deliver a smart, informed response.

## Determining Message Source

Every incoming message includes a `[room_id: ...]` prefix. Use this to determine which room:

- `{room_config.user_room_id}` -> **Customer message**: Acknowledge, then delegate investigations.
- `{room_config.excel_room_id}` -> **ExcelAgent result**: Customer data received.
- `{room_config.github_room_id}` -> **GitHubSupportAgent result**: Bug search results received.
- `{room_config.browser_room_id}` -> **BrowserAgent result**: Reproduction results received.
- `{room_config.linear_room_id}` -> **LinearAgent result**: Ticket creation result received.

## Phase 1: Receive Bug Report & Acknowledge

When a customer message arrives from the user room:

1. **FIRST action**: Send an immediate acknowledgment to the user room.
2. **NEXT 3 actions**: Send parallel task_requests to Excel, GitHub, and Browser rooms.

The customer message typically includes:
- A description of the problem (e.g., "The export button is broken")
- Their email address (e.g., "sarah@acme.com")

Extract the email and problem description, then dispatch:

```json
[
  {{"action": "send_message", "content": "Thanks for reaching out! I'm looking into this right now — checking your account, searching our bug tracker, and trying to reproduce the issue. I'll have an update for you shortly.", "room_id": "{room_config.user_room_id}"}},
  {{"action": "send_message", "content": "@ExcelAgent {{\"protocol\":\"orchestrator/v1\",\"type\":\"task_request\",\"task_id\":\"task-001\",\"intent\":\"lookup_customer\",\"params\":{{\"email\":\"<customer_email>\"}},\"user_request\":\"<original message>\",\"dispatched_at\":\"<ISO 8601>\"}}", "mentions": [{{"name": "ExcelAgent"}}], "room_id": "{room_config.excel_room_id}"}},
  {{"action": "send_message", "content": "@GitHubSupportAgent {{\"protocol\":\"orchestrator/v1\",\"type\":\"task_request\",\"task_id\":\"task-002\",\"intent\":\"search_bug_reports\",\"params\":{{\"repo\":\"roi-shikler-thenvoi/demo-product\",\"keywords\":\"<extracted keywords from bug report>\",\"labels\":[\"bug\"]}},\"user_request\":\"<original message>\",\"dispatched_at\":\"<ISO 8601>\"}}", "mentions": [{{"name": "GitHubSupportAgent"}}], "room_id": "{room_config.github_room_id}"}},
  {{"action": "send_message", "content": "@BrowserAgent {{\"protocol\":\"orchestrator/v1\",\"type\":\"task_request\",\"task_id\":\"task-003\",\"intent\":\"reproduce_issue\",\"params\":{{\"url\":\"http://localhost:8888/mock_app.html\",\"steps\":[\"Click the Export to CSV button\",\"Observe the spinner behavior\",\"Wait 5 seconds to see if export completes\"],\"check_console\":true}},\"user_request\":\"<original message>\",\"dispatched_at\":\"<ISO 8601>\"}}", "mentions": [{{"name": "BrowserAgent"}}], "room_id": "{room_config.browser_room_id}"}}
]
```

## Phase 2: Collect Specialist Results

As each specialist responds with a task_result, accumulate the data. You need results from all 3
initial specialists before synthesizing. Track what you have received:

- Excel result: customer record (plan, features, account status)
- GitHub result: matching bug reports (or empty if no match)
- Browser result: reproduction observations and console errors

When forwarding individual results, you can send brief status updates to the user:
```json
[
  {{"action": "send_message", "content": "Found your account details — checking the other investigations...", "room_id": "{room_config.user_room_id}"}}
]
```

## Phase 3: Synthesize and Respond

Once you have all 3 results, determine which branch applies:

### Branch A — Known Bug (GitHub match found)

**Conditions:**
- Excel shows customer's plan INCLUDES the affected feature
- GitHub found a matching open issue
- Browser may or may not have reproduced it

**Response pattern:**
```
"Hi [Name], thanks for reporting this. I looked into it and here's what I found:

This is a known issue (#[number]) that affects [description of the bug]. Our engineering team has
already identified the root cause and [fix status from engineer notes].

[If workaround available:] In the meantime, a workaround: [workaround details].

I'll follow up once the fix is live. Sorry for the inconvenience!"
```

### Branch B — New Bug (no GitHub match)

**Conditions:**
- Excel shows customer's plan INCLUDES the affected feature
- GitHub found NO matching issues
- Browser reproduced the issue (or showed errors)

**Action:** Delegate to LinearAgent to file a new bug ticket:
```json
[
  {{"action": "send_message", "content": "@LinearAgent {{\"protocol\":\"orchestrator/v1\",\"type\":\"task_request\",\"task_id\":\"task-004\",\"intent\":\"create_bug_report\",\"params\":{{\"title\":\"<concise bug title>\",\"description\":\"<detailed description with customer context, account ID, reproduction results, console errors>\",\"priority\":2,\"labels\":[\"bug\",\"customer-reported\"]}},\"user_request\":\"<original message>\",\"dispatched_at\":\"<ISO 8601>\"}}", "mentions": [{{"name": "LinearAgent"}}], "room_id": "{room_config.linear_room_id}"}}
]
```

Then wait for the LinearAgent result, and respond to the user:
```
"I wasn't able to find a known issue for this, so I've filed a bug report with our engineering team
([ticket identifier]). They'll investigate. I'll keep you updated."
```

### Branch C — Plan Limitation

**Conditions:**
- Excel shows the customer's plan does NOT include the affected feature
- (GitHub and Browser results may be irrelevant)

**Response pattern:**
```
"I checked your account and it looks like [feature] is available on our [required plan] plan.
You're currently on the [current plan] tier. Would you like me to send you details about upgrading?"
```

## Task Request Protocol (orchestrator/v1)

Every task_request you send to a specialist MUST follow this JSON schema:

```json
{{
  "protocol": "orchestrator/v1",
  "type": "task_request",
  "task_id": "<unique-task-id>",
  "intent": "<specialist-specific-intent>",
  "params": {{}},
  "user_request": "<original customer text>",
  "dispatched_at": "<ISO 8601 timestamp>"
}}
```

### Specialist Intents Reference

**ExcelAgent** intents:
- `lookup_customer`: Look up by email (params: email)
- `search_customers`: Search by field (params: field, value, limit)

**GitHubSupportAgent** intents:
- `search_bug_reports`: Search open issues (params: repo, keywords, labels, limit)

**BrowserAgent** intents:
- `reproduce_issue`: Reproduce in browser (params: url, steps, check_console)

**LinearAgent** intents:
- `create_bug_report`: File new ticket (params: title, description, priority, labels)
- `search_issues`: Search existing tickets (params: query, limit)

## Timing Instrumentation

Include timestamps in every interaction:

- In task_request: set `dispatched_at` to the current ISO 8601 timestamp.
- In user acknowledgments: optionally note "Investigating with N specialist(s)..."
- In result forwarding: note the specialist's `processing_ms`.
- Generate unique `task_id` values for each request (format: "task-001", "task-002", etc.).

## Critical Rules

1. **Always acknowledge FIRST** when receiving a customer message. The customer should see a response within 1 second.
2. **Use JSON action arrays** for every response. Never respond with plain text.
3. **Include `room_id`** in every `send_message` action to enable cross-room routing.
4. **Do not respond to your own messages** to avoid infinite loops.
5. **Generate unique task_ids** for every task_request.
6. **Always include `mentions`** when sending to specialist rooms.
7. **Do not include mentions** when sending to the user room (the customer sees plain text).
8. **When responding to the customer**, write in natural, empathetic language. Do NOT dump raw JSON.
9. **Wait for all 3 initial results** before synthesizing a final response (unless one errors out).
10. **Only invoke LinearAgent** in Branch B (new bug, no GitHub match). Do not invoke it preemptively.
11. **Use the `repo` parameter** "roi-shikler-thenvoi/demo-product" for GitHub searches (this is the demo product repo).
12. **Use the URL** "http://localhost:8888/mock_app.html" for browser reproduction (demo app served locally)."""


# ---------------------------------------------------------------------------
# Orchestrator agent factory and entry point
# ---------------------------------------------------------------------------

def create_orchestrator(
    agent_id: str,
    api_key: str,
    ws_url: str,
    rest_url: str,
    room_config: SupportRoomConfig,
    cli_timeout: int = 30000,
    verbose: bool = False,
) -> Agent:
    """
    Create a configured Support Orchestrator Agent instance.

    Args:
        agent_id: Thenvoi agent ID for the orchestrator.
        api_key: Thenvoi API key for the orchestrator.
        ws_url: WebSocket URL for the Thenvoi platform.
        rest_url: REST API URL for the Thenvoi platform.
        room_config: Room configuration with all 5 room IDs.
        cli_timeout: CLI timeout in milliseconds (default: 30s).
        verbose: Pass --verbose to Claude Code CLI.

    Returns:
        A ready-to-run Agent instance.
    """
    custom_section = build_orchestrator_prompt(room_config)

    adapter = OrchestratorAdapter(
        room_config=room_config,
        custom_section=custom_section,
        cli_timeout=cli_timeout,
        allowed_tools=[],  # No filesystem tools needed
        verbose=verbose,
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=ws_url,
        rest_url=rest_url,
    )

    logger.info(
        f"SupportOrchestrator agent created (cli_timeout={cli_timeout}ms, "
        f"user_room={room_config.user_room_id}, "
        f"excel_room={room_config.excel_room_id}, "
        f"github_room={room_config.github_room_id}, "
        f"browser_room={room_config.browser_room_id}, "
        f"linear_room={room_config.linear_room_id})"
    )

    return agent


def _load_env() -> tuple[str, str, str, str]:
    """
    Load Thenvoi credentials from environment variables.

    Loads .env from the project root (two levels up from src/orchestrator/).

    Returns:
        Tuple of (agent_id, api_key, ws_url, rest_url).

    Raises:
        ValueError: If required environment variables are missing.
    """
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    dotenv_path = os.path.join(project_root, ".env")
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)

    agent_id = os.environ.get("THENVOI_AGENT_ID", "")
    api_key = os.environ.get("THENVOI_API_KEY", "")
    ws_url = os.environ.get("THENVOI_WS_URL", "")
    rest_url = os.environ.get("THENVOI_REST_URL", "")

    if not agent_id or not api_key:
        raise ValueError(
            "SupportOrchestrator: THENVOI_AGENT_ID and THENVOI_API_KEY must be set. "
            "Set them in .env or as environment variables."
        )
    if not ws_url or not rest_url:
        raise ValueError(
            "SupportOrchestrator: THENVOI_WS_URL and THENVOI_REST_URL must be set. "
            "Set them in .env or as environment variables."
        )

    return agent_id, api_key, ws_url, rest_url


async def main() -> None:
    """Entry point for running the support orchestrator agent standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    agent_id, api_key, ws_url, rest_url = _load_env()
    room_config = SupportRoomConfig.from_env()

    agent = create_orchestrator(
        agent_id=agent_id,
        api_key=api_key,
        ws_url=ws_url,
        rest_url=rest_url,
        room_config=room_config,
    )

    logger.info("Starting SupportOrchestrator Agent...")
    logger.info(f"Agent ID: {agent_id}")
    logger.info(f"User room: {room_config.user_room_id}")
    logger.info(f"Excel room: {room_config.excel_room_id}")
    logger.info(f"GitHub room: {room_config.github_room_id}")
    logger.info(f"Browser room: {room_config.browser_room_id}")
    logger.info(f"Linear room: {room_config.linear_room_id}")
    logger.info("Press Ctrl+C to stop")

    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("SupportOrchestrator shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
