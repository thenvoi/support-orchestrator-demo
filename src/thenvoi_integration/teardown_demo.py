"""
Teardown script for the support orchestrator demo.

Deletes all registered agents (with force=true), which also cleans up
associated chat room participation and execution history.

Usage:
    python -m thenvoi_integration.teardown_demo

    # Or from the project root:
    python src/thenvoi_integration/teardown_demo.py

Requires:
    THENVOI_API_KEY (user key, thnv_u_...) in .env or environment.
    THENVOI_REST_URL in .env or environment (defaults to https://app.thenvoi.com).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from thenvoi_integration.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.dirname(_THIS_DIR)
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> tuple[str, str]:
    """
    Load base URL and user API key from environment.

    Tries THENVOI_USER_API_KEY first (set by setup_demo.py to preserve the
    user key when THENVOI_API_KEY is overwritten with an agent key), then
    falls back to THENVOI_API_KEY.

    Returns:
        Tuple of (base_url, api_key).

    Raises:
        SystemExit: If required configuration is missing.
    """
    if os.path.exists(_ENV_PATH):
        load_dotenv(_ENV_PATH)

    # setup_demo.py saves the user key as THENVOI_USER_API_KEY.
    api_key = os.environ.get("THENVOI_USER_API_KEY", "")
    if not api_key:
        api_key = os.environ.get("THENVOI_API_KEY", "")

    base_url = os.environ.get("THENVOI_REST_URL", "https://app.thenvoi.com")

    if not api_key:
        print(
            "ERROR: No user API key found. Set THENVOI_USER_API_KEY or "
            "THENVOI_API_KEY in .env or as an environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not api_key.startswith("thnv_u_"):
        print(
            f"WARNING: API key does not start with 'thnv_u_'. "
            f"Teardown requires a User API key, not an Agent key.",
            file=sys.stderr,
        )

    return base_url, api_key


# ---------------------------------------------------------------------------
# Main teardown
# ---------------------------------------------------------------------------

async def teardown() -> None:
    """
    Delete all agents owned by the authenticated user.

    Uses ``force=True`` to remove agents even if they have execution
    history. Chat room participation is cleaned up automatically when
    agents are deleted.
    """
    base_url, api_key = _load_config()

    print("=" * 60)
    print("  Support Orchestrator Demo - Teardown")
    print("=" * 60)
    print(f"\nPlatform: {base_url}")
    print()

    async with AgentRegistry(base_url, api_key) as registry:
        # -- Step 1: List existing agents --------------------------------------

        print("Step 1: Listing registered agents...")
        print("-" * 40)

        try:
            agents = await registry.list_agents()
        except Exception as e:
            print(f"  ERROR listing agents: {e}", file=sys.stderr)
            sys.exit(1)

        if not agents:
            print("  No agents found. Nothing to tear down.")
            return

        for agent in agents:
            agent_id = agent.get("id", "?")
            name = agent.get("name", "?")
            print(f"  {name:20s}  id={agent_id}")

        print()

        # -- Step 2: Confirm deletion ------------------------------------------

        print(f"Step 2: Deleting {len(agents)} agent(s) (force=true)...")
        print("-" * 40)

        deleted_count = 0
        failed_count = 0

        for agent in agents:
            agent_id = agent.get("id", "")
            name = agent.get("name", "unknown")

            if not agent_id:
                print(f"  SKIP: Agent with no ID: {agent}")
                continue

            try:
                await registry.delete_agent(agent_id, force=True)
                print(f"  Deleted: {name:20s} (id={agent_id})")
                deleted_count += 1
            except Exception as e:
                print(f"  FAILED: {name:20s} (id={agent_id}): {e}", file=sys.stderr)
                failed_count += 1

    print()
    print("=" * 60)
    print("  Teardown Complete!")
    print("=" * 60)
    print()
    print(f"  Deleted: {deleted_count} agent(s)")
    if failed_count:
        print(f"  Failed:  {failed_count} agent(s)")
    print()
    print("Note: Chat rooms are cleaned up when agents are deleted.")
    print("      You may want to manually clean room IDs from .env.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(teardown())
