"""
Setup script for the support orchestrator demo.

Creates agents and rooms on the Thenvoi platform, persists credentials
to agent_config.yaml and room IDs to .env.

Steps:
    1. Register 5 agents (SupportOrchestrator, ExcelAgent, GitHubSupportAgent,
       BrowserAgent, LinearAgent).
    2. Save agent IDs and one-time API keys to agent_config.yaml.
    3. Create 5 rooms (R-user-support, R-excel, R-github-support, R-browser, R-linear).
    4. Add correct participants to each room.
    5. Append room IDs to .env.
    6. Print summary.

Usage:
    python -m thenvoi_integration.setup_demo

    # Or from the project root:
    python src/thenvoi_integration/setup_demo.py

Requires:
    THENVOI_API_KEY (user key, thnv_u_...) in .env or environment.
    THENVOI_REST_URL in .env or environment (defaults to https://app.thenvoi.com).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import yaml
from dotenv import load_dotenv

from thenvoi_integration.agent_registry import AgentRegistry
from thenvoi_integration.room_manager import RoomManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Resolve project root (two levels up from src/thenvoi_integration/).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.dirname(_THIS_DIR)
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)

_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
_CONFIG_PATH = os.path.join(_SRC_DIR, "config", "agent_config.yaml")

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

AGENT_DEFS = [
    {
        "key": "support_orchestrator",
        "name": "SupportOrchestrator",
        "description": "Customer support hub orchestrator for multi-agent investigation",
    },
    {
        "key": "excel",
        "name": "ExcelAgent",
        "description": "Customer data lookup specialist (reads from Excel)",
    },
    {
        "key": "github_support",
        "name": "GitHubSupportAgent",
        "description": "GitHub bug triage specialist for customer support",
    },
    {
        "key": "browser",
        "name": "BrowserAgent",
        "description": "Browser automation specialist for issue reproduction",
    },
    {
        "key": "linear",
        "name": "LinearAgent",
        "description": "Linear issue tracking specialist for bug report filing",
    },
]

# Room topology: room label -> list of agent keys that should be participants.
# The user (room creator) is automatically an owner/participant.
# The orchestrator is present in ALL rooms.
ROOM_TOPOLOGY = {
    "R-user-support": ["support_orchestrator"],
    "R-excel": ["support_orchestrator", "excel"],
    "R-github-support": ["support_orchestrator", "github_support"],
    "R-browser": ["support_orchestrator", "browser"],
    "R-linear": ["support_orchestrator", "linear"],
}

# Maps room labels to .env variable names.
ROOM_ENV_VARS = {
    "R-user-support": "SUPPORT_USER_ROOM_ID",
    "R-excel": "SUPPORT_EXCEL_ROOM_ID",
    "R-github-support": "SUPPORT_GITHUB_ROOM_ID",
    "R-browser": "SUPPORT_BROWSER_ROOM_ID",
    "R-linear": "SUPPORT_LINEAR_ROOM_ID",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> tuple[str, str]:
    """
    Load base URL and user API key from environment.

    Returns:
        Tuple of (base_url, api_key).

    Raises:
        SystemExit: If required configuration is missing.
    """
    if os.path.exists(_ENV_PATH):
        load_dotenv(_ENV_PATH)

    api_key = os.environ.get("THENVOI_API_KEY", "")
    base_url = os.environ.get("THENVOI_REST_URL", "https://app.thenvoi.com")

    if not api_key:
        print(
            "ERROR: THENVOI_API_KEY is not set. "
            "Add it to .env or export it as an environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not api_key.startswith("thnv_u_"):
        print(
            f"WARNING: THENVOI_API_KEY does not start with 'thnv_u_'. "
            f"Setup requires a User API key, not an Agent key.",
            file=sys.stderr,
        )

    return base_url, api_key


def _save_agent_config(agents: dict[str, dict]) -> None:
    """
    Update agent_config.yaml with registered agent IDs and API keys.

    Preserves existing fields and only overwrites agent_id and api_key.

    Args:
        agents: Dict mapping agent key -> {"id": ..., "api_key": ...}.
    """
    # Load existing config to preserve structure and extra fields.
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    if "agents" not in config:
        config["agents"] = {}

    for agent_key, agent_data in agents.items():
        if agent_key not in config["agents"]:
            config["agents"][agent_key] = {}
        config["agents"][agent_key]["agent_id"] = agent_data["id"]
        config["agents"][agent_key]["api_key"] = agent_data["api_key"]

    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    logger.info("Agent config saved to %s", _CONFIG_PATH)


def _append_env_vars(env_vars: dict[str, str]) -> None:
    """
    Append or update environment variables in the .env file.

    If a variable already exists in the file, its value is updated in place.
    New variables are appended at the end.

    Args:
        env_vars: Dict mapping variable name -> value.
    """
    existing_lines: list[str] = []
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, "r") as f:
            existing_lines = f.readlines()

    # Track which vars we've updated in-place.
    updated = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        # Check if this line sets one of our variables.
        matched = False
        for var_name, var_value in env_vars.items():
            if stripped.startswith(f"{var_name}=") or stripped.startswith(f"{var_name} ="):
                new_lines.append(f"{var_name}={var_value}\n")
                updated.add(var_name)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    # Append header comment and new vars that weren't updated in-place.
    remaining = {k: v for k, v in env_vars.items() if k not in updated}
    if remaining:
        # Ensure there's a blank line before the new section.
        if new_lines and new_lines[-1].strip():
            new_lines.append("\n")
        new_lines.append("# Room IDs (auto-generated by setup_demo.py)\n")
        for var_name, var_value in remaining.items():
            new_lines.append(f"{var_name}={var_value}\n")

    with open(_ENV_PATH, "w") as f:
        f.writelines(new_lines)

    logger.info("Environment variables saved to %s", _ENV_PATH)


# ---------------------------------------------------------------------------
# Main setup
# ---------------------------------------------------------------------------

async def setup() -> None:
    """
    Run the full demo setup sequence.

    1. Register agents and save credentials.
    2. Create rooms and add participants.
    3. Write configuration files.
    4. Print summary.
    """
    base_url, api_key = _load_config()

    print("=" * 60)
    print("  Support Orchestrator Demo - Setup")
    print("=" * 60)
    print(f"\nPlatform: {base_url}")
    print(f"Config:   {_CONFIG_PATH}")
    print(f"Env:      {_ENV_PATH}")
    print()

    # -- Step 1: Register agents -----------------------------------------------

    print("Step 1: Registering agents...")
    print("-" * 40)

    # agent_key -> {"id": ..., "api_key": ...}
    registered_agents: dict[str, dict] = {}

    async with AgentRegistry(base_url, api_key) as registry:
        for agent_def in AGENT_DEFS:
            key = agent_def["key"]
            name = agent_def["name"]
            description = agent_def["description"]

            try:
                result = await registry.register_agent(name, description)
                agent_info = result.get("agent", {})
                credentials = result.get("credentials", {})

                agent_id = agent_info.get("id", "")
                agent_api_key = credentials.get("api_key", "")

                if not agent_id or not agent_api_key:
                    print(f"  ERROR: Registration for {name} returned incomplete data.")
                    print(f"         Response: {result}")
                    sys.exit(1)

                registered_agents[key] = {
                    "id": agent_id,
                    "api_key": agent_api_key,
                    "name": name,
                }

                print(f"  {name:25s} -> id={agent_id}")
                print(f"  {'':25s}    key={agent_api_key[:20]}...")

            except Exception as e:
                print(f"  ERROR registering {name}: {e}", file=sys.stderr)
                sys.exit(1)

    print()

    # -- Step 2: Save agent credentials ----------------------------------------

    print("Step 2: Saving agent credentials to agent_config.yaml...")
    _save_agent_config(registered_agents)
    print(f"  Saved to {_CONFIG_PATH}")
    print()

    # Also save orchestrator credentials as THENVOI_AGENT_ID / THENVOI_API_KEY
    # in .env so the orchestrator.py entry point can find them.
    orch = registered_agents["support_orchestrator"]
    _append_env_vars({
        "THENVOI_AGENT_ID": orch["id"],
        # Preserve the user key for future admin operations.
        "THENVOI_USER_API_KEY": api_key,
    })

    # -- Step 3: Create rooms --------------------------------------------------

    print("Step 3: Creating rooms...")
    print("-" * 40)

    # room_label -> room_id
    room_ids: dict[str, str] = {}

    async with RoomManager(base_url, api_key) as rm:
        for room_label in ROOM_TOPOLOGY:
            try:
                room = await rm.create_room(title=room_label)
                room_id = room.get("id", "")
                if not room_id:
                    print(f"  ERROR: Room creation for {room_label} returned no ID.")
                    sys.exit(1)

                room_ids[room_label] = room_id
                print(f"  {room_label:20s} -> {room_id}")

            except Exception as e:
                print(f"  ERROR creating {room_label}: {e}", file=sys.stderr)
                sys.exit(1)

        print()

        # -- Step 4: Add participants to rooms ---------------------------------

        print("Step 4: Adding participants to rooms...")
        print("-" * 40)

        for room_label, agent_keys in ROOM_TOPOLOGY.items():
            room_id = room_ids[room_label]
            for agent_key in agent_keys:
                agent = registered_agents[agent_key]
                agent_id = agent["id"]
                agent_name = agent["name"]

                try:
                    await rm.add_participant(room_id, agent_id, role="member")
                    print(f"  {room_label:20s} <- {agent_name} ({agent_id})")
                except Exception as e:
                    print(
                        f"  ERROR adding {agent_name} to {room_label}: {e}",
                        file=sys.stderr,
                    )
                    sys.exit(1)

    print()

    # -- Step 5: Write room IDs to .env ----------------------------------------

    print("Step 5: Saving room IDs to .env...")
    env_room_vars = {}
    for room_label, env_var in ROOM_ENV_VARS.items():
        env_room_vars[env_var] = room_ids[room_label]

    _append_env_vars(env_room_vars)
    print(f"  Saved to {_ENV_PATH}")
    print()

    # -- Step 6: Summary -------------------------------------------------------

    print("=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print()
    print("Registered Agents:")
    for key, agent in registered_agents.items():
        print(f"  {agent['name']:25s}  id={agent['id']}")
    print()
    print("Created Rooms:")
    for label, room_id in room_ids.items():
        participants = ROOM_TOPOLOGY[label]
        participant_names = [registered_agents[k]["name"] for k in participants]
        print(f"  {label:20s}  id={room_id}")
        print(f"  {'':20s}  participants: user (owner) + {', '.join(participant_names)}")
    print()
    print("Configuration files updated:")
    print(f"  {_CONFIG_PATH}")
    print(f"  {_ENV_PATH}")
    print()
    print("Next steps:")
    print("  1. Generate demo data:       python demo_data/generate_customers.py")
    print("  2. Serve mock app:           cd demo_data && python -m http.server 8888")
    print("  3. Start the orchestrator:   python -m orchestrator.orchestrator")
    print("  4. Start specialist agents:  (see README.md for per-agent commands)")
    print("  5. Send a message in the Thenvoi UI to the R-user-support room")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(setup())
