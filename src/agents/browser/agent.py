"""
Browser specialist agent for the support orchestrator demo.

Handles issue reproduction intents delegated by the orchestrator:
- reproduce_issue: Simulate browser-based reproduction using a mock tool

Uses a LangChain tool (simulate_browser_reproduction) to generate realistic
mock reproduction data for demo purposes.

Run standalone:
    THENVOI_AGENT_ID=<id> THENVOI_API_KEY=<key> python -m agents.browser.agent

Or:
    python src/agents/browser/agent.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from langchain_core.tools import tool

# Ensure src/ is on the path when run standalone
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from agents.base_specialist import BaseSpecialist

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Demo / mock browser reproduction tool
# ---------------------------------------------------------------------------

@tool
def simulate_browser_reproduction(url: str, steps: str, check_console: bool = True) -> str:
    """Simulate browser-based issue reproduction for demo purposes.

    Args:
        url: The page URL to navigate to
        steps: JSON array of reproduction steps (e.g. '["Click Export to CSV", "Observe spinner"]')
        check_console: Whether to check browser console for errors (default: True)
    """
    import json as _json
    try:
        step_list = _json.loads(steps) if isinstance(steps, str) else steps
    except (ValueError, TypeError):
        step_list = [steps] if isinstance(steps, str) else ["Unknown steps"]

    # Generate realistic mock reproduction data based on the steps
    observations = [f"Navigated to {url}"]
    console_errors = []
    reproduced = False

    for step in step_list:
        step_lower = step.lower()
        observations.append(f"Executed: {step}")

        if any(kw in step_lower for kw in ["export", "csv", "download"]):
            observations.append("Spinner appeared on the button")
            observations.append("Spinner continued indefinitely — export never completed")
            reproduced = True
        elif any(kw in step_lower for kw in ["click", "press", "tap"]):
            observations.append("Element responded to interaction")
        elif any(kw in step_lower for kw in ["wait", "observe"]):
            observations.append("Waited 5 seconds — no change in page state")

    if check_console and reproduced:
        console_errors = [
            "TimeoutError: Export query exceeded 30s limit",
            "[ExportService] Export failed: query timeout on datasets with >500 rows",
        ]

    screenshot_desc = (
        "Dashboard page with export button showing infinite spinner"
        if reproduced
        else f"Page at {url} in normal state"
    )

    return _json.dumps({
        "reproduced": reproduced,
        "observations": observations,
        "console_errors": console_errors,
        "screenshot_description": screenshot_desc,
    })


# ---------------------------------------------------------------------------
# Browser specialist
# ---------------------------------------------------------------------------

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
    def additional_tools(self) -> list:
        """Provide the mock browser reproduction tool to the LangGraph adapter."""
        return [simulate_browser_reproduction]

    def build_custom_section(self) -> str:
        """
        Build the custom_section prompt for browser-based issue reproduction.

        Instructs the agent to use the simulate_browser_reproduction tool and
        then respond via thenvoi_send_message with orchestrator/v1 protocol.
        """
        min_delay, max_delay = self.delay_range
        return f"""You are {self.agent_name}, a specialist agent for {self.domain} operations.

## Role

You operate in a dedicated Thenvoi chat room with the SupportOrchestrator agent. Your sole job is to
receive task_request messages from @SupportOrchestrator, reproduce reported issues using the
`simulate_browser_reproduction` tool, and respond with detailed reproduction results.

## Supported Intents

{self._build_intents_section()}

## Protocol

When you receive a message from @SupportOrchestrator containing a JSON task_request:

1. **Parse** the task_request JSON to extract `task_id`, `intent`, `params`, and `dispatched_at`.
2. **Validate** the intent is one you support. If not, respond with a task_result with status "error".
3. **Call the `simulate_browser_reproduction` tool** with the params from the request:
   - `url`: the page URL from params
   - `steps`: a JSON-encoded array of the reproduction steps from params
   - `check_console`: whether to check console errors (default true)
4. **Parse the tool result** (JSON string) to get the reproduction data.
5. **Respond** with a task_result JSON via `thenvoi_send_message`.

## How to Use the Reproduction Tool

Call `simulate_browser_reproduction` with the parameters extracted from the task_request:

    simulate_browser_reproduction(
        url="https://app.example.com/dashboard",
        steps='["Click Export to CSV button", "Observe spinner behavior"]',
        check_console=True
    )

The tool returns a JSON string with:
- `reproduced` (bool): Whether the issue was reproduced
- `observations` (list[str]): What was observed at each step
- `console_errors` (list[str]): Any console errors found
- `screenshot_description` (str): Description of the final page state

Use the returned data as the `result` field in your task_result response.

## Response Format

After calling `simulate_browser_reproduction`, use the `thenvoi_send_message` tool to send the
task_result back to the orchestrator:

    thenvoi_send_message(
        content='{{"protocol":"orchestrator/v1","type":"task_result","task_id":"<from request>","status":"success","result":{{<reproduction data from tool>}},"started_at":"<ISO 8601>","completed_at":"<ISO 8601>","processing_ms":<elapsed ms>}}',
        mentions=['SupportOrchestrator']
    )

For errors:

    thenvoi_send_message(
        content='{{"protocol":"orchestrator/v1","type":"task_result","task_id":"<from request>","status":"error","error":{{"code":"<ERROR_CODE>","message":"<description>"}},"started_at":"<ISO 8601>","completed_at":"<ISO 8601>","processing_ms":<elapsed ms>}}',
        mentions=['SupportOrchestrator']
    )

## Timing

- `started_at`: The ISO 8601 timestamp when you begin processing (use current time).
- `completed_at`: The ISO 8601 timestamp when processing completes. This should be
  {min_delay}-{max_delay} seconds after started_at to simulate realistic browser work.
- `processing_ms`: The difference in milliseconds between started_at and completed_at.

## Rules

1. **Only respond to messages from @SupportOrchestrator** containing task_request JSON. Ignore everything else.
2. **Always use the `thenvoi_send_message` tool** to send your response (never plain text).
3. **Always include timing data** (started_at, completed_at, processing_ms).
4. **Always call `simulate_browser_reproduction`** to get reproduction data before responding.
5. **Do not respond to your own messages** to avoid loops.
6. **Be thorough**: pass check_console=True even if the visible behavior seems normal."""


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
