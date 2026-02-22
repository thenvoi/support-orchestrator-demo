"""
Excel specialist agent for the support orchestrator demo.

Handles customer data lookup intents delegated by the orchestrator:
- lookup_customer: Find a customer record by email address
- search_customers: Search customers by any field (plan, status, company, etc.)

Uses LangChain tools with pandas to read the demo customers.xlsx file.

Run standalone:
    THENVOI_AGENT_ID=<id> THENVOI_API_KEY=<key> python -m agents.excel.agent

Or:
    python src/agents/excel/agent.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

import pandas as pd
from langchain_core.tools import tool

# Ensure src/ is on the path when run standalone
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from agents.base_specialist import BaseSpecialist

logger = logging.getLogger(__name__)

# Resolve path to the customers.xlsx file relative to project root.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_CUSTOMERS_XLSX = os.path.join(_PROJECT_ROOT, "demo_data", "customers.xlsx")


# ---------------------------------------------------------------------------
# LangChain tools for customer data operations
# ---------------------------------------------------------------------------

@tool
def lookup_customer(email: str) -> str:
    """Look up a customer record by email address from the customer database."""
    try:
        df = pd.read_excel(_CUSTOMERS_XLSX)
        row = df[df['email'] == email]
        if row.empty:
            return json.dumps({"found": False, "error": f"No customer found with email: {email}"})
        return json.dumps(row.iloc[0].to_dict(), default=str)
    except Exception as e:
        return json.dumps({"found": False, "error": str(e)})


@tool
def search_customers(field: str, value: str, limit: int = 10) -> str:
    """Search customers by any field value (e.g. plan, status, company)."""
    try:
        df = pd.read_excel(_CUSTOMERS_XLSX)
        matches = df[df[field].str.contains(value, case=False, na=False)]
        return json.dumps(matches.head(limit).to_dict(orient='records'), default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


class ExcelSpecialist(BaseSpecialist):
    """
    Customer data lookup specialist agent.

    Operates in a dedicated chat room with the SupportOrchestrator, receiving
    task_request messages for customer data queries and responding with
    data read from customers.xlsx via pandas LangChain tools.
    """

    @property
    def agent_name(self) -> str:
        return "ExcelAgent"

    @property
    def domain(self) -> str:
        return "customer data lookup from Excel spreadsheets"

    @property
    def supported_intents(self) -> dict[str, str]:
        return {
            "lookup_customer": (
                "Look up a customer record by email address. Params: email (str). "
                "Returns: customer object with email, name, company, plan, status, "
                "features, account_id, signup_date. Returns error if not found."
            ),
            "search_customers": (
                "Search customers by any field value. Params: field (str, e.g. 'plan', "
                "'status', 'company'), value (str, the value to match), limit (int, "
                "optional, default: 10). "
                "Returns: list of matching customer objects."
            ),
        }

    @property
    def delay_range(self) -> tuple[int, int]:
        return (1, 3)

    @property
    def additional_tools(self) -> list:
        """Provide the lookup_customer and search_customers LangChain tools."""
        return [lookup_customer, search_customers]

    def build_custom_section(self) -> str:
        """
        Build a fully custom prompt that uses LangChain tools to query customers.xlsx.

        Overrides the base class entirely to provide Excel-specific instructions.
        """
        return f"""You are {self.agent_name}, a specialist agent for {self.domain} operations.

## Role

You operate in a dedicated Thenvoi chat room with the SupportOrchestrator agent. Your sole job is to
receive task_request messages from @SupportOrchestrator, query customer data from an Excel file using
the provided tools, and respond with task_result messages containing the data.

## Supported Intents

{self._build_intents_section()}

## Protocol

When you receive a message from @SupportOrchestrator containing a JSON task_request:

1. **Parse** the task_request JSON to extract `task_id`, `intent`, `params`, and `dispatched_at`.
2. **Validate** the intent is one you support. If not, respond with a task_result with status "error".
3. **Call the appropriate tool** based on the intent:
   - For `lookup_customer`: call the `lookup_customer` tool with the `email` param.
   - For `search_customers`: call the `search_customers` tool with `field`, `value`, and optionally `limit` params.
4. **Format** the tool result into the response schema described for each intent.
5. **Respond** with a task_result JSON using the `thenvoi_send_message` tool.

## Response Format

To respond, use the `thenvoi_send_message` tool with the task_result JSON as content and mentions=['SupportOrchestrator'].

For a successful result, call the tool like this:

    thenvoi_send_message(
        content='{{"protocol":"orchestrator/v1","type":"task_result","task_id":"<from request>","status":"success","result":{{<tool result data>}},"started_at":"<ISO 8601>","completed_at":"<ISO 8601>","processing_ms":<elapsed ms>}}',
        mentions=['SupportOrchestrator']
    )

For errors (including customer not found):

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
4. **Always query the real Excel file** via the provided tools. Never fabricate or mock data.
5. **If a tool call fails or returns no results**, return a task_result with status "error" and include the error message.
6. **Do not respond to your own messages** to avoid loops."""


async def main() -> None:
    """Entry point for running the Excel agent standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    specialist = ExcelSpecialist()
    await specialist.run()


if __name__ == "__main__":
    asyncio.run(main())
