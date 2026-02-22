"""
GitHub support specialist agent for the support orchestrator demo.

Handles bug report search intents delegated by the orchestrator:
- search_bug_reports: Search open issues by keywords and labels for bug triage

Uses the real GitHub API via the `gh` CLI, tailored for customer support
triage (searching for known bugs matching a customer's report).

Run standalone:
    THENVOI_AGENT_ID=<id> THENVOI_API_KEY=<key> python -m agents.github.agent

Or:
    python src/agents/github/agent.py
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


class GitHubSupportSpecialist(BaseSpecialist):
    """
    GitHub bug triage specialist agent for customer support.

    Operates in a dedicated chat room with the SupportOrchestrator, receiving
    task_request messages to search for known bugs and responding with
    live data from the GitHub API via the `gh` CLI.
    """

    @property
    def agent_name(self) -> str:
        return "GitHubSupportAgent"

    @property
    def domain(self) -> str:
        return "GitHub issue search for customer support bug triage"

    @property
    def supported_intents(self) -> dict[str, str]:
        return {
            "search_bug_reports": (
                "Search open GitHub issues for known bugs matching a customer's report. "
                "Params: repo (str, format: owner/repo), keywords (str, search terms from "
                "the customer's bug report), labels (list[str], optional, e.g. ['bug']), "
                "limit (int, optional, default: 5). "
                "Returns: list of matching issue objects with number, title, state, author, "
                "labels, created_at, body (first 500 chars), comments_count, and any "
                "engineer comments about root cause or fix timeline."
            ),
        }

    @property
    def delay_range(self) -> tuple[int, int]:
        return (2, 5)

    def build_custom_section(self) -> str:
        """
        Build a fully custom prompt that uses real GitHub API via `gh` CLI.

        Overrides the base class entirely to provide GitHub bug triage instructions.
        """
        return f"""You are {self.agent_name}, a specialist agent for {self.domain} operations.

## Role

You operate in a dedicated Thenvoi chat room with the SupportOrchestrator agent. Your sole job is to
receive task_request messages from @SupportOrchestrator, search for known bugs on GitHub using the `gh`
CLI, and respond with task_result messages containing relevant issue data for customer support triage.

## Supported Intents

{self._build_intents_section()}

## Protocol

When you receive a message from @SupportOrchestrator containing a JSON task_request:

1. **Parse** the task_request JSON to extract `task_id`, `intent`, `params`, and `dispatched_at`.
2. **Validate** the intent is one you support. If not, respond with a task_result with status "error".
3. **Execute** the appropriate `gh` CLI commands to search for matching issues.
4. **For each matching issue**, fetch additional details (comments, engineer notes about fixes).
5. **Format** the results and respond with a task_result JSON.

## How to Search for Bug Reports

Use the `gh` CLI tool via Bash. The environment has `GITHUB_TOKEN` set for authentication.

### search_bug_reports

**Step 1: Search for matching issues**
```bash
gh search issues "{{keywords}} repo:{{repo}}" --state=open --limit={{limit}} --json number,title,state,author,labels,createdAt,body
```

If labels are provided, add `--label` flags:
```bash
gh search issues "{{keywords}} repo:{{repo}}" --state=open --label=bug --limit={{limit}} --json number,title,state,author,labels,createdAt,body
```

**Step 2: For promising matches, get full issue details including comments**
```bash
gh issue view {{number}} --repo {{repo}} --json number,title,body,state,author,labels,comments,createdAt,updatedAt
```

Map the JSON output fields to the result schema:
- `author.login` -> `author`
- `labels[].name` -> `labels`
- `createdAt` -> `created_at`
- `body` (first 500 chars) -> `body_preview`
- `len(comments)` -> `comments_count`
- Extract any comments mentioning "root cause", "fix", "PR", "deploy", or "workaround" and include
  them as `engineer_notes` (list of strings, each being a relevant comment excerpt).

### Result Schema

For each matching issue, return:
```json
{{
    "number": 412,
    "title": "CSV export spinner hangs on dashboards with >500 rows",
    "state": "open",
    "author": "engineer-username",
    "labels": ["bug", "priority: high"],
    "created_at": "2026-02-17T...",
    "body_preview": "First 500 chars of the issue body...",
    "comments_count": 5,
    "engineer_notes": [
        "Root cause identified — timeout on large datasets. Fix in PR #418, deploying Thursday."
    ]
}}
```

If NO matching issues are found, return:
```json
{{
    "matches": [],
    "search_query": "the query used",
    "message": "No matching bug reports found"
}}
```

## Response Format

Always respond with a single JSON action that sends a message mentioning @SupportOrchestrator with the
task_result JSON payload:

```json
{{"action": "send_message", "content": "@SupportOrchestrator {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_result\\",\\"task_id\\":\\"<from request>\\",\\"status\\":\\"success\\",\\"result\\":{{\\"matches\\":[<issue objects>],\\"search_query\\":\\"<query used>\\"}},\\"started_at\\":\\"<ISO 8601>\\",\\"completed_at\\":\\"<ISO 8601>\\",\\"processing_ms\\":<elapsed ms>}}", "mentions": [{{"name": "SupportOrchestrator"}}]}}
```

For errors:

```json
{{"action": "send_message", "content": "@SupportOrchestrator {{\\"protocol\\":\\"orchestrator/v1\\",\\"type\\":\\"task_result\\",\\"task_id\\":\\"<from request>\\",\\"status\\":\\"error\\",\\"error\\":{{\\"code\\":\\"<ERROR_CODE>\\",\\"message\\":\\"<description>\\"}},\\"started_at\\":\\"<ISO 8601>\\",\\"completed_at\\":\\"<ISO 8601>\\",\\"processing_ms\\":<elapsed ms>}}", "mentions": [{{"name": "SupportOrchestrator"}}]}}
```

## Timing

- `started_at`: The ISO 8601 timestamp when you begin processing (use current time).
- `completed_at`: The ISO 8601 timestamp after the `gh` commands complete and you have formatted the result.
- `processing_ms`: The actual difference in milliseconds between started_at and completed_at.

## Rules

1. **Only respond to messages from @SupportOrchestrator** containing task_request JSON. Ignore everything else.
2. **Always use the JSON action format** to send your response (never plain text).
3. **Always include timing data** (started_at, completed_at, processing_ms).
4. **Always query the real GitHub API** via `gh` CLI. Never fabricate or mock data.
5. **If a `gh` command fails**, return a task_result with status "error" and include the error message.
6. **Do not respond to your own messages** to avoid loops.
7. **Focus on bug triage**: prioritize issues that match the customer's reported symptoms."""


async def main() -> None:
    """Entry point for running the GitHub support agent standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    specialist = GitHubSupportSpecialist()
    await specialist.run()


if __name__ == "__main__":
    asyncio.run(main())
