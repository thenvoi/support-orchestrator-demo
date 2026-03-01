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
5. Conditionally invokes LinearAgent (Branch B: new bug -> file ticket)

Uses a custom adapter subclass (OrchestratorAdapter) that extends
LangGraphAdapter with cross-room messaging via custom LangChain tools.

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

from agents.base_specialist import create_llm
from dotenv import load_dotenv
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from thenvoi import Agent, SessionConfig
from thenvoi.adapters import LangGraphAdapter
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
# Custom adapter with cross-room messaging via LangChain tools
# ---------------------------------------------------------------------------

class OrchestratorAdapter(LangGraphAdapter):
    """
    Extended LangGraphAdapter with cross-room messaging via custom tools.

    Creates dynamic LangChain tools for each specialist room that use
    temporary AgentTools instances to send messages to the correct room.
    """

    def __init__(
        self,
        room_config: SupportRoomConfig,
        custom_section: str | None = None,
    ):
        # We use the simple pattern; cross-room tools are injected dynamically
        # in on_message via self.additional_tools.
        super().__init__(
            llm=create_llm(),
            checkpointer=InMemorySaver(),
            custom_section=custom_section or "",
        )
        self.room_config = room_config
        self._cross_room_tools: list = []

    async def on_message(
        self,
        msg,
        tools,  # AgentToolsProtocol bound to current room
        history,
        participants_msg,
        contacts_msg,
        *,
        is_session_bootstrap,
        room_id,
    ):
        """Override to inject cross-room tools and fix system message ordering."""
        # Create cross-room tools dynamically (they need the live tools.rest reference)
        self._cross_room_tools = self._build_cross_room_tools(tools)

        # Temporarily add cross-room tools to additional_tools
        original_tools = self.additional_tools
        self.additional_tools = original_tools + self._cross_room_tools

        # Fix for Anthropic "Received multiple non-consecutive system messages":
        # When is_session_bootstrap=True and there's history, the parent inserts
        # ("system", system_prompt), then history, then ("system", participants_msg),
        # which creates non-consecutive system messages. Merge participants/contacts
        # into _system_prompt temporarily so they stay in the first system block.
        original_prompt = self._system_prompt
        extras = []
        if participants_msg:
            extras.append(f"\n\n## Current Room Participants\n{participants_msg}")
        if contacts_msg:
            extras.append(f"\n\n## Contacts\n{contacts_msg}")
        if extras:
            self._system_prompt = original_prompt + "".join(extras)

        try:
            await super().on_message(
                msg, tools, history,
                participants_msg=None,  # merged into _system_prompt
                contacts_msg=None,      # merged into _system_prompt
                is_session_bootstrap=is_session_bootstrap, room_id=room_id,
            )
        finally:
            self.additional_tools = original_tools
            self._system_prompt = original_prompt

    def _build_cross_room_tools(self, tools) -> list:
        """Build LangChain tools for cross-room messaging."""
        room_config = self.room_config

        async def _send_to_room(
            room_id: str, room_label: str, content: str, mentions_str: str = "",
        ) -> str:
            """Send a message to a specific room via temporary AgentTools."""
            try:
                target_tools = AgentTools(
                    room_id=room_id,
                    rest=tools.rest,
                    participants=None,
                )
                # Load participants for mention resolution
                try:
                    target_participants = (
                        await tools.rest.agent_api_participants
                        .list_agent_chat_participants(chat_id=room_id)
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
                except Exception:
                    pass

                mentions = (
                    [m.strip() for m in mentions_str.split(",") if m.strip()]
                    if mentions_str
                    else []
                )
                await target_tools.send_message(content, mentions)
                return f"Message sent to {room_label}"
            except Exception as e:
                return f"Error sending to {room_label}: {e}"

        # --- Per-room tool functions ---

        async def send_to_user_room(content: str) -> str:
            """Send a message to the user support room (customer-facing)."""
            return await _send_to_room(
                room_config.user_room_id, "user-room", content, "",
            )

        async def send_to_excel_room(
            content: str, mentions: str = "ExcelAgent",
        ) -> str:
            """Send a task_request to the Excel specialist room. Include @ExcelAgent mention."""
            return await _send_to_room(
                room_config.excel_room_id, "excel-room", content, mentions,
            )

        async def send_to_github_room(
            content: str, mentions: str = "GitHubSupportAgent",
        ) -> str:
            """Send a task_request to the GitHub specialist room. Include @GitHubSupportAgent mention."""
            return await _send_to_room(
                room_config.github_room_id, "github-room", content, mentions,
            )

        async def send_to_browser_room(
            content: str, mentions: str = "BrowserAgent",
        ) -> str:
            """Send a task_request to the Browser specialist room. Include @BrowserAgent mention."""
            return await _send_to_room(
                room_config.browser_room_id, "browser-room", content, mentions,
            )

        async def send_to_linear_room(
            content: str, mentions: str = "LinearAgent",
        ) -> str:
            """Send a task_request to the Linear specialist room. Include @LinearAgent mention."""
            return await _send_to_room(
                room_config.linear_room_id, "linear-room", content, mentions,
            )

        return [
            StructuredTool.from_function(
                coroutine=send_to_user_room,
                name="send_to_user_room",
                description=(
                    "Send a message to the customer in the user support room. "
                    "Use for acknowledgments and final responses."
                ),
            ),
            StructuredTool.from_function(
                coroutine=send_to_excel_room,
                name="send_to_excel_room",
                description=(
                    "Send a task_request to ExcelAgent in the Excel room "
                    "for customer data lookup."
                ),
            ),
            StructuredTool.from_function(
                coroutine=send_to_github_room,
                name="send_to_github_room",
                description=(
                    "Send a task_request to GitHubSupportAgent in the GitHub room "
                    "for bug search."
                ),
            ),
            StructuredTool.from_function(
                coroutine=send_to_browser_room,
                name="send_to_browser_room",
                description=(
                    "Send a task_request to BrowserAgent in the Browser room "
                    "for issue reproduction."
                ),
            ),
            StructuredTool.from_function(
                coroutine=send_to_linear_room,
                name="send_to_linear_room",
                description=(
                    "Send a task_request to LinearAgent in the Linear room "
                    "for filing bug tickets."
                ),
            ),
        ]


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

## Cross-Room Tools

You have dedicated tools for sending messages to each room:

- `send_to_user_room(content)` — Send a message to the customer (no mentions needed).
- `send_to_excel_room(content, mentions)` — Send to ExcelAgent (default mention: "ExcelAgent").
- `send_to_github_room(content, mentions)` — Send to GitHubSupportAgent (default mention: "GitHubSupportAgent").
- `send_to_browser_room(content, mentions)` — Send to BrowserAgent (default mention: "BrowserAgent").
- `send_to_linear_room(content, mentions)` — Send to LinearAgent (default mention: "LinearAgent").

Use these tools for ALL cross-room communication. The tools handle room routing and mention resolution automatically.

## Determining Message Source

Every incoming message includes a `[room_id: ...]` prefix. Use this to determine which room:

- `{room_config.user_room_id}` -> **Customer message**: Acknowledge, then delegate investigations.
- `{room_config.excel_room_id}` -> **ExcelAgent result**: Customer data received.
- `{room_config.github_room_id}` -> **GitHubSupportAgent result**: Bug search results received.
- `{room_config.browser_room_id}` -> **BrowserAgent result**: Reproduction results received.
- `{room_config.linear_room_id}` -> **LinearAgent result**: Ticket creation result received.

## Phase 1: Receive Bug Report & Acknowledge

When a customer message arrives from the user room:

1. **FIRST**: Call `send_to_user_room` with an immediate acknowledgment.
2. **NEXT**: Call `send_to_excel_room`, `send_to_github_room`, and `send_to_browser_room` with parallel task_requests.

The customer message typically includes:
- A description of the problem (e.g., "The export button is broken")
- Their email address (e.g., "sarah@acme.com")

Extract the email and problem description, then dispatch:

```
Call send_to_user_room(content="Thanks for reaching out! I'm looking into this right now — checking your account, searching our bug tracker, and trying to reproduce the issue. I'll have an update for you shortly.")

Call send_to_excel_room(content="@ExcelAgent {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_request\\",\\"task_id\\":\\"task-001\\",\\"intent\\":\\"lookup_customer\\",\\"params\\":{{\\"email\\":\\"<customer_email>\\"}},\\"user_request\\":\\"<original message>\\",\\"dispatched_at\\":\\"<ISO 8601>\\"}}")

Call send_to_github_room(content="@GitHubSupportAgent {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_request\\",\\"task_id\\":\\"task-002\\",\\"intent\\":\\"search_bug_reports\\",\\"params\\":{{\\"repo\\":\\"roi-shikler-thenvoi/demo-product\\",\\"keywords\\":\\"<extracted keywords from bug report>\\",\\"labels\\":[\\"bug\\"]}},\\"user_request\\":\\"<original message>\\",\\"dispatched_at\\":\\"<ISO 8601>\\"}}")

Call send_to_browser_room(content="@BrowserAgent {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_request\\",\\"task_id\\":\\"task-003\\",\\"intent\\":\\"reproduce_issue\\",\\"params\\":{{\\"url\\":\\"http://localhost:8888/mock_app.html\\",\\"steps\\":[\\"Click the Export to CSV button\\",\\"Observe the spinner behavior\\",\\"Wait 5 seconds to see if export completes\\"],\\"check_console\\":true}},\\"user_request\\":\\"<original message>\\",\\"dispatched_at\\":\\"<ISO 8601>\\"}}")
```

## Phase 2: Collect Specialist Results

As each specialist responds with a task_result, accumulate the data. You need results from all 3
initial specialists before synthesizing. Track what you have received:

- Excel result: customer record (plan, features, account status)
- GitHub result: matching bug reports (or empty if no match)
- Browser result: reproduction observations and console errors

When forwarding individual results, you can send brief status updates to the user:
```
Call send_to_user_room(content="Found your account details — checking the other investigations...")
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
Call send_to_user_room(content="Hi [Name], thanks for reporting this. I looked into it and here's what I found:\\n\\nThis is a known issue (#[number]) that affects [description of the bug]. Our engineering team has already identified the root cause and [fix status from engineer notes].\\n\\n[If workaround available:] In the meantime, a workaround: [workaround details].\\n\\nI'll follow up once the fix is live. Sorry for the inconvenience!")
```

### Branch B — New Bug (no GitHub match)

**Conditions:**
- Excel shows customer's plan INCLUDES the affected feature
- GitHub found NO matching issues
- Browser reproduced the issue (or showed errors)

**Action:** Delegate to LinearAgent to file a new bug ticket:
```
Call send_to_linear_room(content="@LinearAgent {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_request\\",\\"task_id\\":\\"task-004\\",\\"intent\\":\\"create_bug_report\\",\\"params\\":{{\\"title\\":\\"<concise bug title>\\",\\"description\\":\\"<detailed description with customer context, account ID, reproduction results, console errors>\\",\\"priority\\":2,\\"labels\\":[\\"bug\\",\\"customer-reported\\"]}},\\"user_request\\":\\"<original message>\\",\\"dispatched_at\\":\\"<ISO 8601>\\"}}")
```

Then wait for the LinearAgent result, and respond to the user:
```
Call send_to_user_room(content="I wasn't able to find a known issue for this, so I've filed a bug report with our engineering team ([ticket identifier]). They'll investigate. I'll keep you updated.")
```

### Branch C — Plan Limitation

**Conditions:**
- Excel shows the customer's plan does NOT include the affected feature
- (GitHub and Browser results may be irrelevant)

**Response pattern:**
```
Call send_to_user_room(content="I checked your account and it looks like [feature] is available on our [required plan] plan. You're currently on the [current plan] tier. Would you like me to send you details about upgrading?")
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

1. **Always acknowledge FIRST** when receiving a customer message. Use `send_to_user_room` for the acknowledgment.
2. **ALWAYS dispatch to ALL 3 specialists** (Excel, GitHub, Browser) for EVERY new customer message. This is MANDATORY — you MUST call `send_to_excel_room`, `send_to_github_room`, AND `send_to_browser_room` for every customer bug report, no exceptions.
3. **NEVER use `thenvoi_send_message` or `thenvoi_send_event`** for any communication. ONLY use the cross-room tools: `send_to_user_room`, `send_to_excel_room`, `send_to_github_room`, `send_to_browser_room`, `send_to_linear_room`.
4. **Always include mentions** when sending to specialist rooms (the tools handle this via the `mentions` parameter with sensible defaults).
5. **Do not include mentions** when sending to the user room (the `send_to_user_room` tool has no mentions parameter).
6. **Do not respond to your own messages** to avoid infinite loops.
7. **Generate unique task_ids** for every task_request.
8. **When responding to the customer**, write in natural, empathetic language. Do NOT dump raw JSON.
9. **Wait for all 3 initial results** before synthesizing a final response (unless one errors out).
10. **Only invoke LinearAgent** in Branch B (new bug, no GitHub match). Do not invoke it preemptively.
11. **Use the `repo` parameter** "roi-shikler-thenvoi/demo-product" for GitHub searches (this is the demo product repo).
12. **Use the URL** "http://localhost:8888/mock_app.html" for browser reproduction (demo app served locally).
13. **Ignore conversation history for dispatch decisions.** Treat EVERY customer message as a brand new investigation. NEVER skip dispatching because you see similar messages or results in history."""


# ---------------------------------------------------------------------------
# Orchestrator agent factory and entry point
# ---------------------------------------------------------------------------

def create_orchestrator(
    agent_id: str,
    api_key: str,
    ws_url: str,
    rest_url: str,
    room_config: SupportRoomConfig,
) -> Agent:
    """
    Create a configured Support Orchestrator Agent instance.

    Args:
        agent_id: Thenvoi agent ID for the orchestrator.
        api_key: Thenvoi API key for the orchestrator.
        ws_url: WebSocket URL for the Thenvoi platform.
        rest_url: REST API URL for the Thenvoi platform.
        room_config: Room configuration with all 5 room IDs.

    Returns:
        A ready-to-run Agent instance.
    """
    custom_section = build_orchestrator_prompt(room_config)

    adapter = OrchestratorAdapter(
        room_config=room_config,
        custom_section=custom_section,
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=ws_url,
        rest_url=rest_url,
        session_config=SessionConfig(enable_context_hydration=False),
    )

    logger.info(
        f"SupportOrchestrator agent created (adapter=LangGraphAdapter, "
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

    # Auto-resolve from agent_config.yaml if not set via env vars
    if not agent_id or not api_key:
        src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        config_path = os.path.join(src_dir, "config", "agent_config.yaml")
        if os.path.exists(config_path):
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            orch_cfg = cfg.get("agents", {}).get("support_orchestrator", {})
            agent_id = agent_id or orch_cfg.get("agent_id", "")
            api_key = api_key or orch_cfg.get("api_key", "")

    ws_url = os.environ.get("THENVOI_WS_URL", "")
    rest_url = os.environ.get("THENVOI_REST_URL", "")

    if not agent_id or not api_key:
        raise ValueError(
            "SupportOrchestrator: Could not resolve credentials. "
            "Set THENVOI_AGENT_ID/THENVOI_API_KEY as env vars, "
            "or ensure agent_config.yaml has an entry for support_orchestrator."
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
