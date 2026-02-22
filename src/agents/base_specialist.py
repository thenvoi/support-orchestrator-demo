"""
Base specialist agent for the support orchestrator demo.

Provides a reusable base that handles:
- Environment variable loading (THENVOI_AGENT_ID, THENVOI_API_KEY, etc.)
- LangGraphAdapter creation with configurable custom_section
- Agent.create() wiring with the adapter
- Standardized specialist prompt template for the orchestrator/v1 protocol

Each specialist subclass only needs to provide:
- Agent name and domain description
- Supported intents and their simulated behaviors
- Delay range for simulated processing

Example:
    class ExcelSpecialist(BaseSpecialist):
        ...

    specialist = ExcelSpecialist()
    await specialist.run()
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from thenvoi import Agent
from thenvoi.adapters import LangGraphAdapter

logger = logging.getLogger(__name__)


def create_llm():
    """
    Create the LLM instance based on available API keys.

    Checks environment variables in order:
    1. ANTHROPIC_API_KEY → ChatAnthropic
    2. OPENAI_API_KEY → ChatOpenAI

    The model name can be overridden with LLM_MODEL env var.

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: If neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is set.
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    model_override = os.environ.get("LLM_MODEL", "")

    if anthropic_key:
        from langchain_anthropic import ChatAnthropic

        model = model_override or "claude-sonnet-4-5-20250929"
        logger.info(f"Using Anthropic LLM: {model}")
        return ChatAnthropic(model=model)

    if openai_key:
        from langchain_openai import ChatOpenAI

        model = model_override or "gpt-5"
        logger.info(f"Using OpenAI LLM: {model}")
        return ChatOpenAI(model=model)

    raise ValueError(
        "No LLM API key found. Set either ANTHROPIC_API_KEY or OPENAI_API_KEY "
        "in your .env file."
    )


class BaseSpecialist(ABC):
    """
    Base class for specialist agents in the hub-and-spoke orchestrator pattern.

    Subclasses must implement:
        - agent_name: Display name for the specialist (e.g., "ExcelAgent")
        - domain: Domain description (e.g., "customer data lookup")
        - supported_intents: Dict mapping intent names to descriptions
        - delay_range: Tuple of (min_seconds, max_seconds) for simulated work
        - build_custom_section(): Returns the full custom_section prompt string
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Display name used in prompt instructions (e.g., 'ExcelAgent')."""
        ...

    @property
    @abstractmethod
    def domain(self) -> str:
        """Domain description for prompt context (e.g., 'customer data lookup')."""
        ...

    @property
    @abstractmethod
    def supported_intents(self) -> dict[str, str]:
        """
        Mapping of intent name to description.

        Example:
            {"lookup_customer": "Look up a customer record by email address"}
        """
        ...

    @property
    @abstractmethod
    def delay_range(self) -> tuple[int, int]:
        """(min_seconds, max_seconds) for simulated processing delay."""
        ...

    @property
    def additional_tools(self) -> list:
        """Additional LangChain tools for the LangGraphAdapter. Override to customize."""
        return []

    def _load_env(self) -> tuple[str, str, str, str]:
        """
        Load Thenvoi credentials from environment variables.

        Loads .env from the project root (two levels up from src/agents/).
        Falls back to existing environment variables if .env is missing.

        Returns:
            Tuple of (agent_id, api_key, ws_url, rest_url)

        Raises:
            ValueError: If required environment variables are missing.
        """
        # Try loading .env from project root
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
                f"{self.agent_name}: THENVOI_AGENT_ID and THENVOI_API_KEY must be set. "
                "Set them in .env or as environment variables."
            )
        if not ws_url or not rest_url:
            raise ValueError(
                f"{self.agent_name}: THENVOI_WS_URL and THENVOI_REST_URL must be set. "
                "Set them in .env or as environment variables."
            )

        return agent_id, api_key, ws_url, rest_url

    def _build_intents_section(self) -> str:
        """Format supported intents as a prompt-friendly list."""
        lines = []
        for intent, description in self.supported_intents.items():
            lines.append(f"- `{intent}`: {description}")
        return "\n".join(lines)

    def build_custom_section(self) -> str:
        """
        Build the custom_section prompt for the LangGraphAdapter.

        This prompt instructs the specialist on how to:
        - Parse incoming task_request messages from the orchestrator
        - Simulate realistic work with a delay
        - Respond with properly formatted task_result JSON
        - Include timing data in every response

        Subclasses can override this for fully custom prompts.
        """
        min_delay, max_delay = self.delay_range
        return f"""You are {self.agent_name}, a specialist agent for {self.domain} operations.

## Role

You operate in a dedicated Thenvoi chat room with the Orchestrator agent. Your sole job is to
receive task_request messages from @SupportOrchestrator, process them, and respond with task_result messages.

## Supported Intents

{self._build_intents_section()}

## Protocol

When you receive a message from @SupportOrchestrator containing a JSON task_request:

1. **Parse** the task_request JSON to extract `task_id`, `intent`, `params`, and `dispatched_at`.
2. **Validate** the intent is one you support. If not, respond with a task_result with status "error".
3. **Simulate processing** by describing what you would do for this intent (you are a demo agent --
   generate realistic mock data). Simulate a delay of {min_delay}-{max_delay} seconds by noting the
   time elapsed in your started_at / completed_at fields.
4. **Respond** with a task_result JSON using the format below.

## Response Format

To respond, use the `thenvoi_send_message` tool with the task_result JSON as content and mentions=['SupportOrchestrator'].

For a successful result, call the tool like this:

    thenvoi_send_message(
        content='{{"protocol":"orchestrator/v1","type":"task_result","task_id":"<from request>","status":"success","result":{{<your result data>}},"started_at":"<ISO 8601>","completed_at":"<ISO 8601>","processing_ms":<elapsed ms>}}',
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
  {min_delay}-{max_delay} seconds after started_at to simulate realistic work.
- `processing_ms`: The difference in milliseconds between started_at and completed_at.

## Rules

1. **Only respond to messages from @SupportOrchestrator** containing task_request JSON. Ignore everything else.
2. **Always use the `thenvoi_send_message` tool** to send your response (never plain text).
3. **Always include timing data** (started_at, completed_at, processing_ms).
4. **Generate realistic mock data** that is plausible for the intent and params.
5. **Do not respond to your own messages** to avoid loops."""

    def create_agent(self) -> Agent:
        """
        Create and return a configured Thenvoi Agent instance.

        Loads environment variables, builds the adapter with the specialist's
        custom_section, and wires everything together via Agent.create().

        Returns:
            A ready-to-run Agent instance.
        """
        agent_id, api_key, ws_url, rest_url = self._load_env()

        custom_section = self.build_custom_section()

        adapter = LangGraphAdapter(
            llm=create_llm(),
            checkpointer=InMemorySaver(),
            custom_section=custom_section,
            additional_tools=self.additional_tools,
        )

        agent = Agent.create(
            adapter=adapter,
            agent_id=agent_id,
            api_key=api_key,
            ws_url=ws_url,
            rest_url=rest_url,
        )

        logger.info(
            f"{self.agent_name} agent created (adapter=LangGraphAdapter, "
            f"delay_range={self.delay_range}s)"
        )

        return agent

    async def run(self) -> None:
        """
        Create and run the specialist agent.

        Blocks until interrupted (Ctrl+C) or the agent is stopped.
        """
        agent = self.create_agent()

        logger.info(f"Starting {self.agent_name}...")
        logger.info(f"Domain: {self.domain}")
        logger.info(f"Supported intents: {list(self.supported_intents.keys())}")
        logger.info(f"Simulated delay: {self.delay_range[0]}-{self.delay_range[1]}s")
        logger.info("Press Ctrl+C to stop")

        try:
            await agent.run()
        except KeyboardInterrupt:
            logger.info(f"{self.agent_name} shutting down...")
