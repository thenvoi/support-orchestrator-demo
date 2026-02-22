"""
Linear specialist agent for the support orchestrator demo.

Handles bug ticket management intents delegated by the orchestrator:
- create_bug_report: Create a new Linear issue with customer context
- search_issues: Search existing Linear issues

Uses Linear MCP tools loaded via ToolSearch at runtime.

This agent is only invoked conditionally (Branch B: when no matching
GitHub issue is found and a new bug needs to be filed).

Run standalone:
    THENVOI_AGENT_ID=<id> THENVOI_API_KEY=<key> python -m agents.linear.agent

Or:
    python src/agents/linear/agent.py
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


class LinearSpecialist(BaseSpecialist):
    """
    Linear issue tracking specialist agent.

    Operates in a dedicated chat room with the SupportOrchestrator, receiving
    task_request messages to create or search Linear issues and responding
    with ticket data.
    """

    @property
    def agent_name(self) -> str:
        return "LinearAgent"

    @property
    def domain(self) -> str:
        return "Linear issue tracking for bug report management"

    @property
    def supported_intents(self) -> dict[str, str]:
        return {
            "create_bug_report": (
                "Create a new Linear issue for a customer-reported bug. Params: title (str), "
                "description (str, detailed bug description including customer context, "
                "reproduction results, and console errors), priority (int, optional, 1=urgent "
                "2=high 3=medium 4=low, default: 2), labels (list[str], optional, e.g. "
                "['bug', 'customer-reported']). "
                "Returns: created issue object with id, identifier (e.g. 'CS-1042'), "
                "title, url, state, priority."
            ),
            "search_issues": (
                "Search existing Linear issues. Params: query (str, search terms), "
                "limit (int, optional, default: 5). "
                "Returns: list of matching issue objects with id, identifier, title, "
                "state, priority, assignee, created_at."
            ),
        }

    @property
    def delay_range(self) -> tuple[int, int]:
        return (2, 4)

    @property
    def allowed_tools(self) -> list[str]:
        """Linear agent needs Bash and ToolSearch to load MCP tools."""
        return ["Bash", "ToolSearch"]

    def build_custom_section(self) -> str:
        """
        Build a fully custom prompt for Linear issue management.

        Overrides the base class entirely to provide MCP tool loading
        and Linear-specific instructions.
        """
        return f"""You are {self.agent_name}, a specialist agent for {self.domain} operations.

## Role

You operate in a dedicated Thenvoi chat room with the SupportOrchestrator agent. Your sole job is to
receive task_request messages from @SupportOrchestrator, create or search Linear issues using Linear
MCP tools, and respond with task_result messages.

You are typically invoked when a customer reports a bug that is NOT already tracked in GitHub —
your job is to file a new bug report in Linear so engineering can investigate.

## Supported Intents

{self._build_intents_section()}

## Protocol

When you receive a message from @SupportOrchestrator containing a JSON task_request:

1. **Parse** the task_request JSON to extract `task_id`, `intent`, `params`, and `dispatched_at`.
2. **Validate** the intent is one you support. If not, respond with a task_result with status "error".
3. **Load Linear tools** using ToolSearch (see below).
4. **Execute** the appropriate Linear operation.
5. **Format** the results and respond with a task_result JSON.

## How to Use Linear Tools

**IMPORTANT**: Before using any Linear tool, you must first load them via ToolSearch.

### Step 1: Load the required MCP tools

For creating issues:
```
ToolSearch query: "+linear create_issue"
```

For searching issues:
```
ToolSearch query: "+linear list_issues"
```

You may also need:
```
ToolSearch query: "+linear get_team"
ToolSearch query: "+linear list_issue_labels"
```

### create_bug_report

After loading tools, call `mcp__plugin_linear_linear__create_issue` with:
- `title`: The issue title from params
- `description`: The detailed description from params (include customer context, reproduction steps, console errors)
- `priority`: Map the numeric priority to Linear's scale (1=urgent, 2=high, 3=medium, 4=low)
- `teamId`: You may need to call `mcp__plugin_linear_linear__list_teams` first to get the team ID

### search_issues

After loading tools, call `mcp__plugin_linear_linear__list_issues` with:
- Filter by the search query terms

### Result Schema

For create_bug_report:
```json
{{
    "id": "issue-uuid",
    "identifier": "CS-1042",
    "title": "CSV export button unresponsive",
    "url": "https://linear.app/team/issue/CS-1042",
    "state": "Triage",
    "priority": 2
}}
```

For search_issues:
```json
{{
    "matches": [
        {{
            "id": "issue-uuid",
            "identifier": "CS-987",
            "title": "Dashboard timeout on large datasets",
            "state": "In Progress",
            "priority": 2,
            "assignee": "engineer-name",
            "created_at": "2026-02-15T..."
        }}
    ]
}}
```

## Response Format

Always respond with a single JSON action that sends a message mentioning @SupportOrchestrator with the
task_result JSON payload:

```json
{{"action": "send_message", "content": "@SupportOrchestrator {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_result\\",\\"task_id\\":\\"<from request>\\",\\"status\\":\\"success\\",\\"result\\":{{<issue data>}},\\"started_at\\":\\"<ISO 8601>\\",\\"completed_at\\":\\"<ISO 8601>\\",\\"processing_ms\\":<elapsed ms>}}", "mentions": [{{"name": "SupportOrchestrator"}}]}}
```

For errors:

```json
{{"action": "send_message", "content": "@SupportOrchestrator {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_result\\",\\"task_id\\":\\"<from request>\\",\\"status\\":\\"error\\",\\"error\\":{{\\"code\\":\\"<ERROR_CODE>\\",\\"message\\":\\"<description>\\"}},\\"started_at\\":\\"<ISO 8601>\\",\\"completed_at\\":\\"<ISO 8601>\\",\\"processing_ms\\":<elapsed ms>}}", "mentions": [{{"name": "SupportOrchestrator"}}]}}
```

## Timing

- `started_at`: The ISO 8601 timestamp when you begin processing (use current time).
- `completed_at`: The ISO 8601 timestamp after the Linear API call completes.
- `processing_ms`: The actual difference in milliseconds between started_at and completed_at.

## Rules

1. **Only respond to messages from @SupportOrchestrator** containing task_request JSON. Ignore everything else.
2. **Always use the JSON action format** to send your response (never plain text).
3. **Always include timing data** (started_at, completed_at, processing_ms).
4. **Always load MCP tools via ToolSearch** before attempting to use them.
5. **Include customer context** in bug descriptions (account ID, plan, reproduction details).
6. **If Linear tools are unavailable or fail**, return a task_result with status "error".
7. **Do not respond to your own messages** to avoid loops."""


async def main() -> None:
    """Entry point for running the Linear agent standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    specialist = LinearSpecialist()
    await specialist.run()


if __name__ == "__main__":
    asyncio.run(main())
