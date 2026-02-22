"""
Linear specialist agent for the support orchestrator demo.

Handles bug ticket management intents delegated by the orchestrator:
- create_bug_report: Create a new Linear issue with customer context
- search_issues: Search existing Linear issues

Uses mock LangChain tools that simulate Linear API responses for demo purposes.

This agent is only invoked conditionally (Branch B: when no matching
GitHub issue is found and a new bug needs to be filed).

Run standalone:
    THENVOI_AGENT_ID=<id> THENVOI_API_KEY=<key> python -m agents.linear.agent

Or:
    python src/agents/linear/agent.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import uuid

# Ensure src/ is on the path when run standalone
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from langchain_core.tools import tool

from agents.base_specialist import BaseSpecialist

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock LangChain tools (simulate Linear API for demo)
# ---------------------------------------------------------------------------


@tool
def create_linear_issue(
    title: str,
    description: str,
    priority: int = 2,
    labels: str = "bug,customer-reported",
) -> str:
    """Create a new Linear issue for a customer-reported bug (demo mock).

    Args:
        title: Issue title
        description: Detailed bug description with customer context
        priority: Priority level (1=urgent, 2=high, 3=medium, 4=low)
        labels: Comma-separated label names
    """
    issue_num = random.randint(1000, 9999)
    issue_id = str(uuid.uuid4())
    identifier = f"CS-{issue_num}"

    return json.dumps(
        {
            "id": issue_id,
            "identifier": identifier,
            "title": title,
            "url": f"https://linear.app/team/issue/{identifier}",
            "state": "Triage",
            "priority": priority,
            "labels": labels.split(",") if labels else [],
            "created": True,
        }
    )


@tool
def search_linear_issues(query: str, limit: int = 5) -> str:
    """Search existing Linear issues (demo mock).

    Args:
        query: Search terms
        limit: Maximum results to return
    """
    # Return empty results for demo - simulates no existing tickets
    return json.dumps(
        {
            "matches": [],
            "query": query,
            "message": "No matching issues found",
        }
    )


# ---------------------------------------------------------------------------
# Specialist class
# ---------------------------------------------------------------------------


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
    def additional_tools(self) -> list:
        """Provide mock Linear tools to the LangGraphAdapter."""
        return [create_linear_issue, search_linear_issues]

    def build_custom_section(self) -> str:
        """
        Build a fully custom prompt for Linear issue management.

        Overrides the base class to provide Linear tool usage instructions
        along with the orchestrator/v1 protocol.
        """
        return f"""You are {self.agent_name}, a specialist agent for {self.domain} operations.

## Role

You operate in a dedicated Thenvoi chat room with the SupportOrchestrator agent. Your sole job is to
receive task_request messages from @SupportOrchestrator, create or search Linear issues using the
Linear tools, and respond with task_result messages.

You are typically invoked when a customer reports a bug that is NOT already tracked in GitHub —
your job is to file a new bug report in Linear so engineering can investigate.

## Supported Intents

{self._build_intents_section()}

## Protocol

When you receive a message from @SupportOrchestrator containing a JSON task_request:

1. **Parse** the task_request JSON to extract `task_id`, `intent`, `params`, and `dispatched_at`.
2. **Validate** the intent is one you support. If not, respond with a task_result with status "error".
3. **Execute** the appropriate Linear operation using the tools described below.
4. **Format** the results and respond with a task_result JSON via `thenvoi_send_message`.

## How to Use Linear Tools

You have two tools available:

### create_linear_issue

Use for the `create_bug_report` intent. Call with:
- `title`: The issue title from params
- `description`: The detailed description from params (include customer context, reproduction steps, console errors)
- `priority`: Map the numeric priority from params (1=urgent, 2=high, 3=medium, 4=low)
- `labels`: Comma-separated label names (default: "bug,customer-reported")

### search_linear_issues

Use for the `search_issues` intent. Call with:
- `query`: The search terms from params
- `limit`: Maximum number of results (default: 5)

## Response Format

After calling the appropriate tool, send the result back to the orchestrator using `thenvoi_send_message`
with mentions=['SupportOrchestrator'].

For a successful result:

    thenvoi_send_message(
        content='{{"protocol":"orchestrator/v1","type":"task_result","task_id":"<from request>","status":"success","result":{{<tool result data>}},"started_at":"<ISO 8601>","completed_at":"<ISO 8601>","processing_ms":<elapsed ms>}}',
        mentions=['SupportOrchestrator']
    )

For errors:

    thenvoi_send_message(
        content='{{"protocol":"orchestrator/v1","type":"task_result","task_id":"<from request>","status":"error","error":{{"code":"<ERROR_CODE>","message":"<description>"}},"started_at":"<ISO 8601>","completed_at":"<ISO 8601>","processing_ms":<elapsed ms>}}',
        mentions=['SupportOrchestrator']
    )

## Timing

- `started_at`: The ISO 8601 timestamp when you begin processing (use current time).
- `completed_at`: The ISO 8601 timestamp after the Linear tool call completes.
- `processing_ms`: The actual difference in milliseconds between started_at and completed_at.

## Rules

1. **Only respond to messages from @SupportOrchestrator** containing task_request JSON. Ignore everything else.
2. **Always use the `thenvoi_send_message` tool** to send your response (never plain text).
3. **Always include timing data** (started_at, completed_at, processing_ms).
4. **Always call the appropriate Linear tool** before responding (do not fabricate results).
5. **Include customer context** in bug descriptions (account ID, plan, reproduction details).
6. **If a Linear tool call fails**, return a task_result with status "error".
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
