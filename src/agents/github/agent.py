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
import json
import logging
import os
import subprocess
import sys

from langchain_core.tools import tool

# Ensure src/ is on the path when run standalone
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from agents.base_specialist import BaseSpecialist

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom LangChain tool – real GitHub issue search via `gh` CLI
# ---------------------------------------------------------------------------

@tool
def search_github_issues(repo: str, keywords: str, labels: str = "bug", limit: int = 5) -> str:
    """Search open GitHub issues for known bugs matching a customer's report.

    Args:
        repo: GitHub repo in owner/repo format
        keywords: Search terms from the customer's bug report
        labels: Comma-separated labels to filter by (default: "bug")
        limit: Max number of results (default: 5)
    """
    try:
        # Step 1: Search for matching issues
        cmd = [
            "gh", "search", "issues", f"{keywords} repo:{repo}",
            "--state=open", f"--limit={limit}",
            "--json", "number,title,state,author,labels,createdAt,body",
        ]
        if labels:
            for label in labels.split(","):
                cmd.extend(["--label", label.strip()])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return json.dumps({"matches": [], "error": result.stderr})

        issues = json.loads(result.stdout) if result.stdout.strip() else []

        # Step 2: For each match, get full details including comments
        enriched = []
        for issue in issues[:3]:  # Limit detailed lookups
            detail_cmd = [
                "gh", "issue", "view", str(issue["number"]),
                "--repo", repo,
                "--json", "number,title,body,state,author,labels,comments,createdAt,updatedAt",
            ]
            detail_result = subprocess.run(detail_cmd, capture_output=True, text=True, timeout=30)
            if detail_result.returncode == 0:
                detail = json.loads(detail_result.stdout)
                engineer_notes = []
                for comment in detail.get("comments", []):
                    body = comment.get("body", "")
                    if any(kw in body.lower() for kw in ["root cause", "fix", "pr", "deploy", "workaround"]):
                        engineer_notes.append(body[:200])
                enriched.append({
                    "number": detail["number"],
                    "title": detail["title"],
                    "state": detail["state"],
                    "author": detail.get("author", {}).get("login", "unknown"),
                    "labels": [l["name"] for l in detail.get("labels", [])],
                    "created_at": detail.get("createdAt", ""),
                    "body_preview": detail.get("body", "")[:500],
                    "comments_count": len(detail.get("comments", [])),
                    "engineer_notes": engineer_notes,
                })
            else:
                enriched.append({
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue.get("state", "open"),
                    "author": issue.get("author", {}).get("login", "unknown"),
                    "labels": [l["name"] for l in issue.get("labels", [])],
                    "created_at": issue.get("createdAt", ""),
                    "body_preview": issue.get("body", "")[:500],
                    "comments_count": 0,
                    "engineer_notes": [],
                })

        return json.dumps({"matches": enriched, "search_query": f"{keywords} repo:{repo}"})
    except Exception as e:
        return json.dumps({"matches": [], "error": str(e)})


# ---------------------------------------------------------------------------
# Specialist class
# ---------------------------------------------------------------------------

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

    @property
    def additional_tools(self) -> list:
        return [search_github_issues]

    def build_custom_section(self) -> str:
        """
        Build a custom prompt that uses the search_github_issues tool for bug triage.

        Overrides the base class to provide GitHub-specific instructions using the
        LangChain tool instead of raw Bash / JSON-action commands.
        """
        return f"""You are {self.agent_name}, a specialist agent for {self.domain} operations.

## Role

You operate in a dedicated Thenvoi chat room with the SupportOrchestrator agent. Your sole job is to
receive task_request messages from @SupportOrchestrator, search for known bugs on GitHub using the
`search_github_issues` tool, and respond with task_result messages containing relevant issue data for
customer support triage.

## Supported Intents

{self._build_intents_section()}

## Protocol

When you receive a message from @SupportOrchestrator containing a JSON task_request:

1. **Parse** the task_request JSON to extract `task_id`, `intent`, `params`, and `dispatched_at`.
2. **Validate** the intent is one you support. If not, respond with a task_result with status "error".
3. **Call the `search_github_issues` tool** with the appropriate parameters extracted from the request
   (repo, keywords, labels, limit).
4. **Format** the tool output into a task_result JSON payload.
5. **Send the response** using the `thenvoi_send_message` tool with mentions=['SupportOrchestrator'].

## How to Search for Bug Reports

Use the `search_github_issues` tool. It accepts:
- `repo` (str): GitHub repo in owner/repo format
- `keywords` (str): Search terms from the customer's bug report
- `labels` (str, optional): Comma-separated labels to filter by (default: "bug")
- `limit` (int, optional): Max number of results (default: 5)

The tool returns a JSON string with `matches` (list of enriched issue objects) and `search_query`.
Each match contains: number, title, state, author, labels, created_at, body_preview, comments_count,
and engineer_notes.

## Response Format

After calling `search_github_issues`, send the result using `thenvoi_send_message`:

For a successful result:

    thenvoi_send_message(
        content='{{"protocol":"orchestrator/v1","type":"task_result","task_id":"<from request>","status":"success","result":<tool output JSON>,"started_at":"<ISO 8601>","completed_at":"<ISO 8601>","processing_ms":<elapsed ms>}}',
        mentions=['SupportOrchestrator']
    )

For errors:

    thenvoi_send_message(
        content='{{"protocol":"orchestrator/v1","type":"task_result","task_id":"<from request>","status":"error","error":{{"code":"<ERROR_CODE>","message":"<description>"}},"started_at":"<ISO 8601>","completed_at":"<ISO 8601>","processing_ms":<elapsed ms>}}',
        mentions=['SupportOrchestrator']
    )

## Timing

- `started_at`: The ISO 8601 timestamp when you begin processing (use current time).
- `completed_at`: The ISO 8601 timestamp after the tool call completes and you have formatted the result.
- `processing_ms`: The actual difference in milliseconds between started_at and completed_at.

## Rules

1. **Only respond to messages from @SupportOrchestrator** containing task_request JSON. Ignore everything else.
2. **Always use the `thenvoi_send_message` tool** to send your response (never plain text).
3. **Always include timing data** (started_at, completed_at, processing_ms).
4. **Always query the real GitHub API** via the `search_github_issues` tool. Never fabricate or mock data.
5. **If the tool returns an error**, return a task_result with status "error" and include the error message.
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
