"""
Shared pytest fixtures for support-orchestrator-demo tests.

Provides:
- Thenvoi REST client (authenticated with user API key)
- Agent config (IDs and API keys from agent_config.yaml)
- Room IDs (from .env)
- Test logger (from test-infrastructure)
"""

import os
import sys
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

# Resolve project root: src/tests/conftest.py -> src/ -> project root
_TESTS_DIR = Path(__file__).parent
_SRC_DIR = _TESTS_DIR.parent
_PROJECT_ROOT = _SRC_DIR.parent
# Logger is bundled locally in src/tests/logger/

# Load .env from the demo project root
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(str(_ENV_PATH))


# ---------------------------------------------------------------------------
# Agent config dataclass
# ---------------------------------------------------------------------------

class AgentConfig:
    """Holds agent IDs and API keys from agent_config.yaml."""

    def __init__(self, config_path: str):
        with open(config_path) as f:
            raw = yaml.safe_load(f)

        agents = raw.get("agents", {})
        self.orchestrator_id = agents["support_orchestrator"]["agent_id"]
        self.orchestrator_key = agents["support_orchestrator"]["api_key"]
        self.excel_id = agents["excel"]["agent_id"]
        self.excel_key = agents["excel"]["api_key"]
        self.github_id = agents["github_support"]["agent_id"]
        self.github_key = agents["github_support"]["api_key"]
        self.browser_id = agents["browser"]["agent_id"]
        self.browser_key = agents["browser"]["api_key"]
        self.linear_id = agents["linear"]["agent_id"]
        self.linear_key = agents["linear"]["api_key"]


class RoomConfig:
    """Holds room IDs from environment variables."""

    def __init__(self):
        self.user_room = os.environ["SUPPORT_USER_ROOM_ID"]
        self.excel_room = os.environ["SUPPORT_EXCEL_ROOM_ID"]
        self.github_room = os.environ["SUPPORT_GITHUB_ROOM_ID"]
        self.browser_room = os.environ["SUPPORT_BROWSER_ROOM_ID"]
        self.linear_room = os.environ["SUPPORT_LINEAR_ROOM_ID"]

    @property
    def all_rooms(self) -> list[str]:
        return [
            self.user_room,
            self.excel_room,
            self.github_room,
            self.browser_room,
            self.linear_room,
        ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def agent_config() -> AgentConfig:
    """Load agent configuration from agent_config.yaml."""
    config_path = _SRC_DIR / "config" / "agent_config.yaml"
    return AgentConfig(str(config_path))


@pytest.fixture(scope="session")
def room_config() -> RoomConfig:
    """Load room configuration from environment variables."""
    return RoomConfig()


@pytest.fixture(scope="session")
def thenvoi_client():
    """
    Create an authenticated Thenvoi REST client (sync).

    Uses the user API key from .env.
    """
    from thenvoi_rest import RestClient

    api_key = os.environ.get("THENVOI_API_KEY") or os.environ.get("THENVOI_USER_API_KEY")
    base_url = os.environ.get("THENVOI_REST_URL", "https://app.thenvoi.com")

    if not api_key:
        pytest.skip("THENVOI_API_KEY not set")

    return RestClient(api_key=api_key, base_url=base_url)


@pytest.fixture(scope="session")
def async_thenvoi_client():
    """
    Create an authenticated Thenvoi REST client (async).
    """
    from thenvoi_rest import AsyncRestClient

    api_key = os.environ.get("THENVOI_API_KEY") or os.environ.get("THENVOI_USER_API_KEY")
    base_url = os.environ.get("THENVOI_REST_URL", "https://app.thenvoi.com")

    if not api_key:
        pytest.skip("THENVOI_API_KEY not set")

    return AsyncRestClient(api_key=api_key, base_url=base_url)


@pytest.fixture(scope="session")
def orchestrator_agent_client(agent_config):
    """
    Create a REST client authenticated as the orchestrator agent.

    Uses the orchestrator's agent API key so we can read specialist rooms.
    """
    from thenvoi_rest import RestClient

    base_url = os.environ.get("THENVOI_REST_URL", "https://app.thenvoi.com")
    return RestClient(api_key=agent_config.orchestrator_key, base_url=base_url)


@pytest.fixture(scope="session")
def test_logger():
    """
    Create a TestLogger from test-infrastructure for rich logging.

    Logs are written to support-orchestrator-demo/logs/.
    """
    from .logger.test_logger import TestLogger

    log_dir = str(_PROJECT_ROOT / "logs")
    logger = TestLogger(log_dir=log_dir)
    with logger:
        logger.log_session_start()
        yield logger
