"""
Provisioning verification tests.

Validates that setup_demo.py correctly provisioned agents and rooms
on the Thenvoi platform. These tests make real API calls.

Markers: requires_api
"""

import pytest


pytestmark = pytest.mark.requires_api


# ---------------------------------------------------------------------------
# Agent provisioning tests
# ---------------------------------------------------------------------------

class TestAgentProvisioning:
    """Verify all 5 agents exist on the platform."""

    def test_agents_registered(self, thenvoi_client):
        """All 5 demo agents should be listed in the user's agents."""
        response = thenvoi_client.human_api_agents.list_my_agents()
        agents = response.data if hasattr(response, "data") else response

        agent_names = set()
        for agent in agents:
            name = agent.name if hasattr(agent, "name") else agent.get("name", "")
            agent_names.add(name)

        expected = {
            "SupportOrchestrator",
            "ExcelAgent",
            "GitHubSupportAgent",
            "BrowserAgent",
            "LinearAgent",
        }

        missing = expected - agent_names
        assert not missing, f"Missing agents on platform: {missing}"

    def test_agent_ids_match_config(self, thenvoi_client, agent_config):
        """Agent IDs on platform match what setup_demo.py saved to agent_config.yaml."""
        response = thenvoi_client.human_api_agents.list_my_agents()
        agents = response.data if hasattr(response, "data") else response

        platform_ids = {}
        for agent in agents:
            name = agent.name if hasattr(agent, "name") else agent.get("name", "")
            aid = agent.id if hasattr(agent, "id") else agent.get("id", "")
            platform_ids[name] = aid

        assert platform_ids.get("SupportOrchestrator") == agent_config.orchestrator_id
        assert platform_ids.get("ExcelAgent") == agent_config.excel_id
        assert platform_ids.get("GitHubSupportAgent") == agent_config.github_id
        assert platform_ids.get("BrowserAgent") == agent_config.browser_id
        assert platform_ids.get("LinearAgent") == agent_config.linear_id


# ---------------------------------------------------------------------------
# Room provisioning tests
# ---------------------------------------------------------------------------

class TestRoomProvisioning:
    """Verify all 5 rooms exist and have correct participants."""

    def test_rooms_exist(self, thenvoi_client, room_config):
        """All 5 rooms should be accessible via the API."""
        for room_id in room_config.all_rooms:
            response = thenvoi_client.human_api_chats.get_my_chat_room(room_id)
            room = response.data if hasattr(response, "data") else response
            rid = room.id if hasattr(room, "id") else room.get("id", "")
            assert rid == room_id, f"Room {room_id} not found or ID mismatch"

    def test_user_room_has_orchestrator(self, thenvoi_client, room_config, agent_config):
        """User room should contain the SupportOrchestrator agent."""
        response = thenvoi_client.human_api_participants.list_my_chat_participants(
            room_config.user_room
        )
        participants = response.data if hasattr(response, "data") else response

        participant_ids = set()
        for p in participants:
            pid = p.id if hasattr(p, "id") else ""
            participant_ids.add(pid)

        assert agent_config.orchestrator_id in participant_ids, \
            "SupportOrchestrator not in user room"

    def test_excel_room_participants(self, thenvoi_client, room_config, agent_config):
        """Excel room should contain SupportOrchestrator + ExcelAgent."""
        response = thenvoi_client.human_api_participants.list_my_chat_participants(
            room_config.excel_room
        )
        participants = response.data if hasattr(response, "data") else response

        participant_ids = set()
        for p in participants:
            pid = p.id if hasattr(p, "id") else ""
            participant_ids.add(pid)

        assert agent_config.orchestrator_id in participant_ids, \
            "SupportOrchestrator not in excel room"
        assert agent_config.excel_id in participant_ids, \
            "ExcelAgent not in excel room"

    def test_github_room_participants(self, thenvoi_client, room_config, agent_config):
        """GitHub room should contain SupportOrchestrator + GitHubSupportAgent."""
        response = thenvoi_client.human_api_participants.list_my_chat_participants(
            room_config.github_room
        )
        participants = response.data if hasattr(response, "data") else response

        participant_ids = set()
        for p in participants:
            pid = p.id if hasattr(p, "id") else ""
            participant_ids.add(pid)

        assert agent_config.orchestrator_id in participant_ids, \
            "SupportOrchestrator not in github room"
        assert agent_config.github_id in participant_ids, \
            "GitHubSupportAgent not in github room"

    def test_browser_room_participants(self, thenvoi_client, room_config, agent_config):
        """Browser room should contain SupportOrchestrator + BrowserAgent."""
        response = thenvoi_client.human_api_participants.list_my_chat_participants(
            room_config.browser_room
        )
        participants = response.data if hasattr(response, "data") else response

        participant_ids = set()
        for p in participants:
            pid = p.id if hasattr(p, "id") else ""
            participant_ids.add(pid)

        assert agent_config.orchestrator_id in participant_ids, \
            "SupportOrchestrator not in browser room"
        assert agent_config.browser_id in participant_ids, \
            "BrowserAgent not in browser room"

    def test_linear_room_participants(self, thenvoi_client, room_config, agent_config):
        """Linear room should contain SupportOrchestrator + LinearAgent."""
        response = thenvoi_client.human_api_participants.list_my_chat_participants(
            room_config.linear_room
        )
        participants = response.data if hasattr(response, "data") else response

        participant_ids = set()
        for p in participants:
            pid = p.id if hasattr(p, "id") else ""
            participant_ids.add(pid)

        assert agent_config.orchestrator_id in participant_ids, \
            "SupportOrchestrator not in linear room"
        assert agent_config.linear_id in participant_ids, \
            "LinearAgent not in linear room"


# ---------------------------------------------------------------------------
# Configuration consistency tests
# ---------------------------------------------------------------------------

class TestConfigConsistency:
    """Verify .env and agent_config.yaml are consistent."""

    def test_env_room_ids_are_valid_uuids(self, room_config):
        """All room IDs in .env should look like valid UUIDs."""
        import re
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )

        for room_id in room_config.all_rooms:
            assert uuid_pattern.match(room_id), \
                f"Room ID '{room_id}' is not a valid UUID"

    def test_agent_ids_are_valid_uuids(self, agent_config):
        """All agent IDs in agent_config.yaml should be valid UUIDs."""
        import re
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )

        ids = [
            agent_config.orchestrator_id,
            agent_config.excel_id,
            agent_config.github_id,
            agent_config.browser_id,
            agent_config.linear_id,
        ]

        for aid in ids:
            assert uuid_pattern.match(aid), f"Agent ID '{aid}' is not a valid UUID"

    def test_agent_api_keys_have_correct_prefix(self, agent_config):
        """All agent API keys should start with 'thnv_a_'."""
        keys = [
            agent_config.orchestrator_key,
            agent_config.excel_key,
            agent_config.github_key,
            agent_config.browser_key,
            agent_config.linear_key,
        ]

        for key in keys:
            assert key.startswith("thnv_a_"), \
                f"Agent API key '{key[:10]}...' doesn't have thnv_a_ prefix"

    def test_all_room_ids_are_unique(self, room_config):
        """No two rooms should share the same ID."""
        rooms = room_config.all_rooms
        assert len(rooms) == len(set(rooms)), \
            "Duplicate room IDs found"

    def test_all_agent_ids_are_unique(self, agent_config):
        """No two agents should share the same ID."""
        ids = [
            agent_config.orchestrator_id,
            agent_config.excel_id,
            agent_config.github_id,
            agent_config.browser_id,
            agent_config.linear_id,
        ]
        assert len(ids) == len(set(ids)), "Duplicate agent IDs found"
