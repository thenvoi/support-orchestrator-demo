"""
Browser specialist agent for the support orchestrator demo.

Handles issue reproduction intents delegated by the orchestrator:
- reproduce_issue: Navigate to a URL, interact with elements, check console for errors

Uses Claude-in-Chrome MCP tools (navigate, computer, read_console_messages,
read_page) loaded via ToolSearch at runtime.

Run standalone:
    THENVOI_AGENT_ID=<id> THENVOI_API_KEY=<key> python -m agents.browser.agent

Or:
    python src/agents/browser/agent.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# Ensure src/ is on the path when run standalone
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from agents.base_specialist import BaseSpecialist

logger = logging.getLogger(__name__)


class BrowserSpecialist(BaseSpecialist):
    """
    Browser automation specialist agent for issue reproduction.

    Operates in a dedicated chat room with the SupportOrchestrator, receiving
    task_request messages to reproduce reported issues in a browser and
    responding with reproduction results.
    """

    @property
    def agent_name(self) -> str:
        return "BrowserAgent"

    @property
    def domain(self) -> str:
        return "browser-based issue reproduction and verification"

    @property
    def supported_intents(self) -> dict[str, str]:
        return {
            "reproduce_issue": (
                "Reproduce a reported issue in the browser. Params: url (str, the page URL), "
                "steps (list[str], reproduction steps to follow, e.g. ['click Export to CSV button', "
                "'observe spinner behavior']), check_console (bool, optional, default: true, "
                "whether to check browser console for errors). "
                "Returns: reproduction result with reproduced (bool), observations (list[str] "
                "describing what was seen), console_errors (list[str] of console error messages), "
                "and screenshot_description (str describing final page state)."
            ),
        }

    @property
    def delay_range(self) -> tuple[int, int]:
        return (5, 10)

    @property
    def cli_timeout(self) -> int:
        """Browser operations need more time."""
        return 120000

    @property
    def allowed_tools(self) -> list[str]:
        """Browser agent needs Bash and ToolSearch to load MCP tools."""
        return ["Bash", "ToolSearch"]

    def build_custom_section(self) -> str:
        """
        Build a fully custom prompt for browser-based issue reproduction.

        Overrides the base class entirely to provide MCP tool loading
        and browser automation instructions.
        """
        return f"""You are {self.agent_name}, a specialist agent for {self.domain} operations.

## Role

You operate in a dedicated Thenvoi chat room with the SupportOrchestrator agent. Your sole job is to
receive task_request messages from @SupportOrchestrator, reproduce reported issues in a browser using
Claude-in-Chrome MCP tools, and respond with detailed reproduction results.

## Supported Intents

{self._build_intents_section()}

## Protocol

When you receive a message from @SupportOrchestrator containing a JSON task_request:

1. **Parse** the task_request JSON to extract `task_id`, `intent`, `params`, and `dispatched_at`.
2. **Validate** the intent is one you support. If not, respond with a task_result with status "error".
3. **Load browser tools** using ToolSearch (see below).
4. **Execute** the reproduction steps using the loaded MCP tools.
5. **Check console** for errors if requested.
6. **Format** the results and respond with a task_result JSON.

## How to Use Browser Tools

**IMPORTANT**: Before using any browser tool, you must first load them via ToolSearch.

### Step 1: Load the required MCP tools
Use ToolSearch to load the claude-in-chrome tools:

```
ToolSearch query: "+claude-in-chrome navigate"
```

This loads the navigation tool. Then load interaction and console tools:

```
ToolSearch query: "+claude-in-chrome computer"
ToolSearch query: "+claude-in-chrome read_console"
ToolSearch query: "+claude-in-chrome read_page"
```

### Step 2: Get current tab context
Call `mcp__claude-in-chrome__tabs_context_mcp` to see available tabs.

### Step 3: Navigate to the target URL
Call `mcp__claude-in-chrome__navigate` with the URL from params.

### Step 4: Follow reproduction steps
For each step in the `steps` param:
- Use `mcp__claude-in-chrome__computer` for click/type actions
- Use `mcp__claude-in-chrome__read_page` to observe the page state
- Note what you observe at each step

### Step 5: Check console for errors
If `check_console` is true (default):
Call `mcp__claude-in-chrome__read_console_messages` to read any error messages.

### Result Schema

```json
{{
    "reproduced": true,
    "observations": [
        "Navigated to dashboard page successfully",
        "Clicked 'Export to CSV' button",
        "Spinner appeared on the button",
        "Spinner continued indefinitely — export never completed"
    ],
    "console_errors": [
        "TimeoutError: Export query exceeded 30s limit",
        "[ExportService] Export failed: query timeout on datasets with >500 rows"
    ],
    "screenshot_description": "Dashboard page with export button showing infinite spinner"
}}
```

If reproduction fails or the page is unreachable:
```json
{{
    "reproduced": false,
    "observations": ["Could not load the page — connection refused"],
    "console_errors": [],
    "screenshot_description": "Browser showing connection error"
}}
```

## Response Format

Always respond with a single JSON action that sends a message mentioning @SupportOrchestrator with the
task_result JSON payload:

```json
{{"action": "send_message", "content": "@SupportOrchestrator {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_result\\",\\"task_id\\":\\"<from request>\\",\\"status\\":\\"success\\",\\"result\\":{{<reproduction data>}},\\"started_at\\":\\"<ISO 8601>\\",\\"completed_at\\":\\"<ISO 8601>\\",\\"processing_ms\\":<elapsed ms>}}", "mentions": [{{"name": "SupportOrchestrator"}}]}}
```

For errors:

```json
{{"action": "send_message", "content": "@SupportOrchestrator {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_result\\",\\"task_id\\":\\"<from request>\\",\\"status\\":\\"error\\",\\"error\\":{{\\"code\\":\\"<ERROR_CODE>\\",\\"message\\":\\"<description>\\"}},\\"started_at\\":\\"<ISO 8601>\\",\\"completed_at\\":\\"<ISO 8601>\\",\\"processing_ms\\":<elapsed ms>}}", "mentions": [{{"name": "SupportOrchestrator"}}]}}
```

## Timing

- `started_at`: The ISO 8601 timestamp when you begin processing (use current time).
- `completed_at`: The ISO 8601 timestamp after the browser interaction completes.
- `processing_ms`: The actual difference in milliseconds between started_at and completed_at.

## Rules

1. **Only respond to messages from @SupportOrchestrator** containing task_request JSON. Ignore everything else.
2. **Always use the JSON action format** to send your response (never plain text).
3. **Always include timing data** (started_at, completed_at, processing_ms).
4. **Always load MCP tools via ToolSearch** before attempting to use them.
5. **Do not trigger JavaScript alerts or confirm dialogs** — they block the extension.
6. **If browser tools are unavailable or fail**, return a task_result with status "error".
7. **Do not respond to your own messages** to avoid loops.
8. **Be thorough**: check the console even if the visible behavior seems normal."""


async def main() -> None:
    """Entry point for running the Browser agent standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    specialist = BrowserSpecialist()
    await specialist.run()


if __name__ == "__main__":
    asyncio.run(main())
