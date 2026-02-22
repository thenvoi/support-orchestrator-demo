"""
Unit tests for support orchestrator demo components.

Tests SupportRoomConfig, build_orchestrator_prompt, and BaseSpecialist
without any API calls.
"""

import os
import pytest


# ---------------------------------------------------------------------------
# SupportRoomConfig tests
# ---------------------------------------------------------------------------

class TestSupportRoomConfig:
    """Test the SupportRoomConfig class."""

    def test_from_env_loads_all_rooms(self, monkeypatch):
        """SupportRoomConfig.from_env() loads all 5 room IDs from env vars."""
        from orchestrator.orchestrator import SupportRoomConfig

        monkeypatch.setenv("SUPPORT_USER_ROOM_ID", "room-user-001")
        monkeypatch.setenv("SUPPORT_EXCEL_ROOM_ID", "room-excel-002")
        monkeypatch.setenv("SUPPORT_GITHUB_ROOM_ID", "room-github-003")
        monkeypatch.setenv("SUPPORT_BROWSER_ROOM_ID", "room-browser-004")
        monkeypatch.setenv("SUPPORT_LINEAR_ROOM_ID", "room-linear-005")

        config = SupportRoomConfig.from_env()

        assert config.user_room_id == "room-user-001"
        assert config.excel_room_id == "room-excel-002"
        assert config.github_room_id == "room-github-003"
        assert config.browser_room_id == "room-browser-004"
        assert config.linear_room_id == "room-linear-005"

    def test_from_env_missing_var_raises(self, monkeypatch):
        """SupportRoomConfig.from_env() raises ValueError when env vars are missing."""
        from orchestrator.orchestrator import SupportRoomConfig

        # Only set some of the required vars
        monkeypatch.setenv("SUPPORT_USER_ROOM_ID", "room-user-001")
        monkeypatch.delenv("SUPPORT_EXCEL_ROOM_ID", raising=False)
        monkeypatch.delenv("SUPPORT_GITHUB_ROOM_ID", raising=False)
        monkeypatch.delenv("SUPPORT_BROWSER_ROOM_ID", raising=False)
        monkeypatch.delenv("SUPPORT_LINEAR_ROOM_ID", raising=False)

        with pytest.raises(ValueError, match="Missing required room configuration"):
            SupportRoomConfig.from_env()

    def test_specialist_room_for_excel(self):
        """specialist_room_for returns excel room for 'excel' keyword."""
        from orchestrator.orchestrator import SupportRoomConfig

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        assert config.specialist_room_for("ExcelAgent") == "e"
        assert config.specialist_room_for("excel") == "e"
        assert config.specialist_room_for("EXCEL") == "e"

    def test_specialist_room_for_github(self):
        """specialist_room_for returns github room for 'github' keyword."""
        from orchestrator.orchestrator import SupportRoomConfig

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        assert config.specialist_room_for("GitHubSupportAgent") == "g"
        assert config.specialist_room_for("github") == "g"

    def test_specialist_room_for_browser(self):
        """specialist_room_for returns browser room for 'browser' keyword."""
        from orchestrator.orchestrator import SupportRoomConfig

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        assert config.specialist_room_for("BrowserAgent") == "b"
        assert config.specialist_room_for("browser") == "b"

    def test_specialist_room_for_linear(self):
        """specialist_room_for returns linear room for 'linear' keyword."""
        from orchestrator.orchestrator import SupportRoomConfig

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        assert config.specialist_room_for("LinearAgent") == "l"
        assert config.specialist_room_for("linear") == "l"

    def test_specialist_room_for_unknown_returns_none(self):
        """specialist_room_for returns None for unknown specialist."""
        from orchestrator.orchestrator import SupportRoomConfig

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        assert config.specialist_room_for("UnknownAgent") is None

    def test_room_label(self):
        """room_label returns human-readable labels for known room IDs."""
        from orchestrator.orchestrator import SupportRoomConfig

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        assert config.room_label("u") == "user-room"
        assert config.room_label("e") == "excel-room"
        assert config.room_label("g") == "github-room"
        assert config.room_label("b") == "browser-room"
        assert config.room_label("l") == "linear-room"
        assert config.room_label("unknown-id") == "unknown-id"


# ---------------------------------------------------------------------------
# build_orchestrator_prompt tests
# ---------------------------------------------------------------------------

class TestBuildOrchestratorPrompt:
    """Test the orchestrator prompt builder."""

    def test_prompt_contains_all_room_ids(self):
        """Prompt includes all 5 room IDs."""
        from orchestrator.orchestrator import SupportRoomConfig, build_orchestrator_prompt

        config = SupportRoomConfig(
            user_room_id="room-user-abc",
            excel_room_id="room-excel-def",
            github_room_id="room-github-ghi",
            browser_room_id="room-browser-jkl",
            linear_room_id="room-linear-mno",
        )

        prompt = build_orchestrator_prompt(config)

        assert "room-user-abc" in prompt
        assert "room-excel-def" in prompt
        assert "room-github-ghi" in prompt
        assert "room-browser-jkl" in prompt
        assert "room-linear-mno" in prompt

    def test_prompt_contains_workflow_phases(self):
        """Prompt describes all 3 workflow phases."""
        from orchestrator.orchestrator import SupportRoomConfig, build_orchestrator_prompt

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        prompt = build_orchestrator_prompt(config)

        assert "Phase 1" in prompt
        assert "Phase 2" in prompt
        assert "Phase 3" in prompt

    def test_prompt_contains_branch_descriptions(self):
        """Prompt describes all 3 decision branches."""
        from orchestrator.orchestrator import SupportRoomConfig, build_orchestrator_prompt

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        prompt = build_orchestrator_prompt(config)

        assert "Branch A" in prompt
        assert "Branch B" in prompt
        assert "Branch C" in prompt

    def test_prompt_contains_specialist_intents(self):
        """Prompt references all specialist intents."""
        from orchestrator.orchestrator import SupportRoomConfig, build_orchestrator_prompt

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        prompt = build_orchestrator_prompt(config)

        assert "lookup_customer" in prompt
        assert "search_bug_reports" in prompt
        assert "reproduce_issue" in prompt
        assert "create_bug_report" in prompt

    def test_prompt_contains_protocol_spec(self):
        """Prompt specifies the orchestrator/v1 protocol."""
        from orchestrator.orchestrator import SupportRoomConfig, build_orchestrator_prompt

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        prompt = build_orchestrator_prompt(config)

        assert "orchestrator/v1" in prompt
        assert "task_request" in prompt
        assert "task_result" in prompt

    def test_prompt_mentions_demo_repo(self):
        """Prompt includes the demo-product GitHub repo."""
        from orchestrator.orchestrator import SupportRoomConfig, build_orchestrator_prompt

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        prompt = build_orchestrator_prompt(config)

        assert "roi-shikler-thenvoi/demo-product" in prompt

    def test_prompt_mentions_mock_app_url(self):
        """Prompt includes the mock app URL for browser reproduction."""
        from orchestrator.orchestrator import SupportRoomConfig, build_orchestrator_prompt

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        prompt = build_orchestrator_prompt(config)

        assert "http://localhost:8888/mock_app.html" in prompt

    def test_prompt_contains_cross_room_tool_names(self):
        """Prompt references the cross-room tool names for LangGraph."""
        from orchestrator.orchestrator import SupportRoomConfig, build_orchestrator_prompt

        config = SupportRoomConfig(
            user_room_id="u", excel_room_id="e",
            github_room_id="g", browser_room_id="b", linear_room_id="l",
        )

        prompt = build_orchestrator_prompt(config)

        assert "send_to_user_room" in prompt
        assert "send_to_excel_room" in prompt
        assert "send_to_github_room" in prompt
        assert "send_to_browser_room" in prompt
        assert "send_to_linear_room" in prompt


# ---------------------------------------------------------------------------
# create_llm tests
# ---------------------------------------------------------------------------

class TestCreateLlm:
    """Test the create_llm() LLM factory function."""

    def test_anthropic_key_returns_chat_anthropic(self, monkeypatch):
        """When ANTHROPIC_API_KEY is set, returns ChatAnthropic."""
        from agents.base_specialist import create_llm

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)

        llm = create_llm()
        assert type(llm).__name__ == "ChatAnthropic"
        assert llm.model == "claude-sonnet-4-5-20250929"

    def test_openai_key_returns_chat_openai(self, monkeypatch):
        """When OPENAI_API_KEY is set (and no Anthropic key), returns ChatOpenAI."""
        from agents.base_specialist import create_llm

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("LLM_MODEL", raising=False)

        llm = create_llm()
        assert type(llm).__name__ == "ChatOpenAI"
        assert llm.model_name == "gpt-5"

    def test_anthropic_takes_priority_over_openai(self, monkeypatch):
        """When both keys are set, Anthropic takes priority."""
        from agents.base_specialist import create_llm

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("LLM_MODEL", raising=False)

        llm = create_llm()
        assert type(llm).__name__ == "ChatAnthropic"

    def test_no_key_raises_value_error(self, monkeypatch):
        """When neither key is set, raises ValueError."""
        from agents.base_specialist import create_llm

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="No LLM API key found"):
            create_llm()

    def test_llm_model_override_anthropic(self, monkeypatch):
        """LLM_MODEL overrides the default Anthropic model name."""
        from agents.base_specialist import create_llm

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("LLM_MODEL", "claude-opus-4-6")

        llm = create_llm()
        assert llm.model == "claude-opus-4-6"

    def test_llm_model_override_openai(self, monkeypatch):
        """LLM_MODEL overrides the default OpenAI model name."""
        from agents.base_specialist import create_llm

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")

        llm = create_llm()
        assert llm.model_name == "gpt-4o"


# ---------------------------------------------------------------------------
# BaseSpecialist tests
# ---------------------------------------------------------------------------

class TestBaseSpecialist:
    """Test the BaseSpecialist base class."""

    def test_build_custom_section_includes_agent_name(self):
        """Custom section includes the agent name."""
        from agents.base_specialist import BaseSpecialist

        class TestSpecialist(BaseSpecialist):
            agent_name = "TestBot"
            domain = "testing"
            supported_intents = {"do_test": "Run a test"}
            delay_range = (1, 3)

        specialist = TestSpecialist()
        prompt = specialist.build_custom_section()

        assert "TestBot" in prompt

    def test_build_custom_section_includes_intents(self):
        """Custom section lists all supported intents."""
        from agents.base_specialist import BaseSpecialist

        class TestSpecialist(BaseSpecialist):
            agent_name = "TestBot"
            domain = "testing"
            supported_intents = {
                "intent_a": "Do thing A",
                "intent_b": "Do thing B",
            }
            delay_range = (2, 5)

        specialist = TestSpecialist()
        prompt = specialist.build_custom_section()

        assert "intent_a" in prompt
        assert "intent_b" in prompt
        assert "Do thing A" in prompt
        assert "Do thing B" in prompt

    def test_build_custom_section_includes_delay_range(self):
        """Custom section mentions the simulated delay range."""
        from agents.base_specialist import BaseSpecialist

        class TestSpecialist(BaseSpecialist):
            agent_name = "TestBot"
            domain = "testing"
            supported_intents = {"do_test": "Run a test"}
            delay_range = (3, 7)

        specialist = TestSpecialist()
        prompt = specialist.build_custom_section()

        assert "3" in prompt
        assert "7" in prompt

    def test_build_custom_section_includes_protocol(self):
        """Custom section references the orchestrator/v1 protocol and thenvoi_send_message."""
        from agents.base_specialist import BaseSpecialist

        class TestSpecialist(BaseSpecialist):
            agent_name = "TestBot"
            domain = "testing"
            supported_intents = {"do_test": "Run a test"}
            delay_range = (1, 2)

        specialist = TestSpecialist()
        prompt = specialist.build_custom_section()

        assert "orchestrator/v1" in prompt
        assert "task_request" in prompt
        assert "task_result" in prompt
        assert "thenvoi_send_message" in prompt

    def test_default_additional_tools(self):
        """Default additional_tools returns an empty list."""
        from agents.base_specialist import BaseSpecialist

        class TestSpecialist(BaseSpecialist):
            agent_name = "TestBot"
            domain = "testing"
            supported_intents = {"do_test": "Run a test"}
            delay_range = (1, 2)

        specialist = TestSpecialist()
        assert specialist.additional_tools == []


# ---------------------------------------------------------------------------
# Specialist agent configuration tests
# ---------------------------------------------------------------------------

class TestSpecialistConfigurations:
    """Test that each specialist agent is configured correctly."""

    def test_excel_agent_config(self):
        """ExcelAgent has correct name, domain, intents, delay, and additional tools."""
        from agents.excel.agent import ExcelSpecialist

        agent = ExcelSpecialist()
        assert agent.agent_name == "ExcelAgent"
        assert "customer" in agent.domain.lower() or "excel" in agent.domain.lower()
        assert "lookup_customer" in agent.supported_intents
        assert agent.delay_range[0] >= 1
        assert agent.delay_range[1] <= 5
        assert len(agent.additional_tools) == 2
        tool_names = [t.name for t in agent.additional_tools]
        assert "lookup_customer" in tool_names
        assert "search_customers" in tool_names

    def test_github_agent_config(self):
        """GitHubSupportAgent has correct name, domain, intents, delay, and additional tools."""
        from agents.github.agent import GitHubSupportSpecialist as GitHubSpecialist

        agent = GitHubSpecialist()
        assert agent.agent_name == "GitHubSupportAgent"
        assert "github" in agent.domain.lower() or "bug" in agent.domain.lower()
        assert "search_bug_reports" in agent.supported_intents
        assert agent.delay_range[0] >= 1
        assert len(agent.additional_tools) == 1
        tool_names = [t.name for t in agent.additional_tools]
        assert "search_github_issues" in tool_names

    def test_browser_agent_config(self):
        """BrowserAgent has correct name, domain, intents, delay, and additional tools."""
        from agents.browser.agent import BrowserSpecialist

        agent = BrowserSpecialist()
        assert agent.agent_name == "BrowserAgent"
        assert "browser" in agent.domain.lower() or "reproduc" in agent.domain.lower()
        assert "reproduce_issue" in agent.supported_intents
        assert len(agent.additional_tools) == 1
        tool_names = [t.name for t in agent.additional_tools]
        assert "simulate_browser_reproduction" in tool_names

    def test_linear_agent_config(self):
        """LinearAgent has correct name, domain, intents, delay, and additional tools."""
        from agents.linear.agent import LinearSpecialist

        agent = LinearSpecialist()
        assert agent.agent_name == "LinearAgent"
        assert "linear" in agent.domain.lower() or "ticket" in agent.domain.lower()
        assert "create_bug_report" in agent.supported_intents
        assert len(agent.additional_tools) == 2
        tool_names = [t.name for t in agent.additional_tools]
        assert "create_linear_issue" in tool_names
        assert "search_linear_issues" in tool_names
