"""
Messaging infrastructure tests.

Tests that messages can be sent to rooms and retrieved via the Thenvoi API.
These tests verify the messaging pipeline works without requiring running agents.

Markers: requires_api
"""

import time

import pytest

from thenvoi_rest import ChatMessageRequest, ChatMessageRequestMentionsItem


pytestmark = pytest.mark.requires_api


class TestMessageSending:
    """Test sending messages to demo rooms."""

    def test_send_message_to_user_room(self, thenvoi_client, room_config, agent_config):
        """User can send a text message to the user-support room."""
        response = thenvoi_client.human_api_messages.send_my_chat_message(
            chat_id=room_config.user_room,
            message=ChatMessageRequest(
                content=f"@SupportOrchestrator [TEST] Hello from test suite at {time.time()}",
                mentions=[
                    ChatMessageRequestMentionsItem(id=agent_config.orchestrator_id),
                ],
            ),
        )

        assert response is not None
        # Response should indicate message was accepted
        data = response.data if hasattr(response, "data") else response
        assert data is not None

    def test_send_message_to_excel_room(self, thenvoi_client, room_config, agent_config):
        """User can send a message to the excel specialist room."""
        response = thenvoi_client.human_api_messages.send_my_chat_message(
            chat_id=room_config.excel_room,
            message=ChatMessageRequest(
                content=f"@ExcelAgent [TEST] ping at {time.time()}",
                mentions=[
                    ChatMessageRequestMentionsItem(id=agent_config.excel_id),
                ],
            ),
        )

        assert response is not None


class TestMessageRetrieval:
    """Test retrieving messages from demo rooms."""

    def test_list_messages_user_room(self, thenvoi_client, room_config):
        """Can retrieve messages from the user-support room."""
        response = thenvoi_client.human_api_messages.list_my_chat_messages(
            chat_id=room_config.user_room,
            page=1,
            page_size=10,
        )

        assert response is not None
        # Should have data attribute with messages list
        messages = response.data if hasattr(response, "data") else response
        assert messages is not None

    def test_list_messages_excel_room(self, thenvoi_client, room_config):
        """Can retrieve messages from the excel room."""
        response = thenvoi_client.human_api_messages.list_my_chat_messages(
            chat_id=room_config.excel_room,
            page=1,
            page_size=10,
        )

        assert response is not None

    def test_list_messages_all_rooms(self, thenvoi_client, room_config):
        """Can retrieve messages from all 5 rooms without errors."""
        for room_id in room_config.all_rooms:
            response = thenvoi_client.human_api_messages.list_my_chat_messages(
                chat_id=room_id,
                page=1,
                page_size=10,
            )
            assert response is not None, f"Failed to list messages in room {room_id}"

    def test_sent_message_appears_in_history(self, thenvoi_client, room_config, agent_config):
        """A sent message should appear when listing room messages."""
        marker = f"TEST_MARKER_{int(time.time())}"

        # Send a message
        thenvoi_client.human_api_messages.send_my_chat_message(
            chat_id=room_config.user_room,
            message=ChatMessageRequest(
                content=f"@SupportOrchestrator {marker}",
                mentions=[
                    ChatMessageRequestMentionsItem(id=agent_config.orchestrator_id),
                ],
            ),
        )

        # Brief pause for message to be persisted
        time.sleep(2)

        # Retrieve messages — search multiple pages since the room may have
        # many messages from previous test runs
        found = False
        for page in range(1, 4):
            response = thenvoi_client.human_api_messages.list_my_chat_messages(
                chat_id=room_config.user_room,
                page=page,
                page_size=50,
            )

            messages = response.data if hasattr(response, "data") else response

            if isinstance(messages, list):
                for msg in messages:
                    content = msg.content if hasattr(msg, "content") else msg.get("content", "")
                    if marker in str(content):
                        found = True
                        break

            if found:
                break

        assert found, f"Sent message with marker '{marker}' not found in room messages"


class TestMessageFormat:
    """Test that message format follows expected patterns."""

    def test_message_has_content_field(self, thenvoi_client, room_config, agent_config):
        """Messages retrieved from rooms should have content fields."""
        # Send a known message first
        thenvoi_client.human_api_messages.send_my_chat_message(
            chat_id=room_config.user_room,
            message=ChatMessageRequest(
                content=f"@SupportOrchestrator format test {time.time()}",
                mentions=[
                    ChatMessageRequestMentionsItem(id=agent_config.orchestrator_id),
                ],
            ),
        )

        time.sleep(1)

        response = thenvoi_client.human_api_messages.list_my_chat_messages(
            chat_id=room_config.user_room,
            page=1,
            page_size=5,
        )

        messages = response.data if hasattr(response, "data") else response

        if isinstance(messages, list) and len(messages) > 0:
            msg = messages[0]
            # Message should have content
            has_content = hasattr(msg, "content") or (isinstance(msg, dict) and "content" in msg)
            assert has_content, "Message missing 'content' field"
