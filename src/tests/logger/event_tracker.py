"""
Event Tracker - Correlates events and builds timelines.

This tracker maintains relationships between events (messages, rooms, agents)
and builds coherent narratives of what happened during tests.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


class EventTracker:
    """
    Tracks relationships between events to build coherent narratives.
    """

    def __init__(self):
        """Initialize event tracker."""
        self.events: List[Dict[str, Any]] = []
        self.message_chains: Dict[str, List[str]] = defaultdict(list)
        self.room_lineage: Dict[str, List[str]] = defaultdict(list)
        self.agent_timeline: Dict[str, List[Dict]] = defaultdict(list)
        self.room_timeline: Dict[str, List[Dict]] = defaultdict(list)
        self.message_responses: Dict[str, Optional[str]] = {}
        self.causality_graph: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

    def add_event(self, event: Dict[str, Any]):
        """
        Track event and update relationships.

        Args:
            event: Event dictionary with event_type and relevant fields
        """
        self.events.append(event)

        event_type = event.get('event_type')

        # Track message chains
        if event_type == 'message_sent':
            self._track_message_chain(event)
        elif event_type == 'message_received':
            self._track_message_response(event)

        # Track room lineage
        elif event_type == 'room_created':
            self._track_room_lineage(event)

        # Track agent activity
        agent_id = event.get('agent_id')
        if agent_id:
            self.agent_timeline[agent_id].append(event)

        # Track room activity
        room_id = event.get('room_id')
        if room_id:
            self.room_timeline[room_id].append(event)

        # Track causality
        self._track_causality(event)

    def _track_message_chain(self, event: Dict[str, Any]):
        """Track message chains within a room."""
        room_id = event.get('room_id')
        message_id = event.get('message_id')
        if room_id and message_id:
            self.message_chains[room_id].append(message_id)

    def _track_message_response(self, event: Dict[str, Any]):
        """Track which message was a response to which request."""
        room_id = event.get('room_id')
        message_id = event.get('message_id')

        if room_id and message_id:
            # Find the most recent user message in this room
            room_messages = self.message_chains[room_id]
            if len(room_messages) > 0:
                # The previous message is likely what triggered this response
                previous_msg = room_messages[-1] if len(room_messages) > 0 else None
                if previous_msg:
                    self.message_responses[message_id] = previous_msg

    def _track_room_lineage(self, event: Dict[str, Any]):
        """Track parent-child relationships between rooms."""
        parent_room = event.get('parent_room')
        room_id = event.get('room_id')

        if parent_room and room_id:
            self.room_lineage[parent_room].append(room_id)

    def _track_causality(self, event: Dict[str, Any]):
        """Track causal relationships between events."""
        event_type = event.get('event_type')
        timestamp = event.get('timestamp')

        # Find events that this event might have caused
        if event_type == 'message_sent':
            # Message sent might cause agent_decision, room_created, message_received
            message_id = event.get('message_id')
            if message_id:
                # Look for subsequent events in same room
                room_id = event.get('room_id')
                for e in self.events[-10:]:  # Look at recent events
                    if e.get('room_id') == room_id and e != event:
                        effect_id = f"{e.get('event_type')}:{e.get('message_id', e.get('room_id'))}"
                        duration = self._calculate_duration(timestamp, e.get('timestamp'))
                        if duration > 0:
                            self.causality_graph[message_id].append((effect_id, duration))

    def _calculate_duration(self, start_ts: str, end_ts: str) -> float:
        """Calculate duration between two ISO timestamps in seconds."""
        try:
            start = datetime.fromisoformat(start_ts.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_ts.replace('Z', '+00:00'))
            return (end - start).total_seconds()
        except:
            return 0.0

    def get_conversation_thread(self, room_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages in a conversation thread.

        Args:
            room_id: Room ID to get messages from

        Returns:
            List of message events in chronological order
        """
        return [
            event for event in self.events
            if event.get('room_id') == room_id
            and event.get('event_type') in ['message_sent', 'message_received']
        ]

    def get_agent_activity_timeline(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        Get all actions by a specific agent.

        Args:
            agent_id: Agent ID to get timeline for

        Returns:
            List of events involving this agent
        """
        return self.agent_timeline[agent_id]

    def get_room_hierarchy(self, root_room_id: str) -> Dict[str, List[str]]:
        """
        Get tree of rooms created from a root room.

        Args:
            root_room_id: Root room ID

        Returns:
            Dictionary mapping room_id to list of child room_ids
        """
        hierarchy = {}
        to_process = [root_room_id]
        processed = set()

        while to_process:
            current = to_process.pop(0)
            if current in processed:
                continue
            processed.add(current)

            children = self.room_lineage.get(current, [])
            hierarchy[current] = children
            to_process.extend(children)

        return hierarchy

    def get_causality_graph(self) -> Dict[str, List[Tuple[str, float]]]:
        """
        Get graph of causal relationships between events.

        Returns:
            Dictionary mapping event_id to list of (caused_event_id, duration_s) tuples
        """
        return dict(self.causality_graph)

    def get_message_flow(self, start_message_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """
        Get the flow of messages starting from a specific message.

        Args:
            start_message_id: Starting message ID
            max_depth: Maximum depth to traverse

        Returns:
            List of message events in causal order
        """
        flow = []
        to_process = [(start_message_id, 0)]
        processed = set()

        while to_process:
            msg_id, depth = to_process.pop(0)
            if msg_id in processed or depth >= max_depth:
                continue
            processed.add(msg_id)

            # Find the message event
            msg_event = next(
                (e for e in self.events if e.get('message_id') == msg_id),
                None
            )
            if msg_event:
                flow.append(msg_event)

                # Find messages that were caused by this message
                caused_events = self.causality_graph.get(msg_id, [])
                for caused_id, _ in caused_events:
                    if caused_id.startswith('message'):
                        caused_msg_id = caused_id.split(':')[1]
                        to_process.append((caused_msg_id, depth + 1))

        return flow

    def get_timeline_summary(self) -> Dict[str, Any]:
        """
        Get summary of the entire event timeline.

        Returns:
            Dictionary with timeline statistics
        """
        event_counts = defaultdict(int)
        for event in self.events:
            event_counts[event.get('event_type')] += 1

        return {
            'total_events': len(self.events),
            'event_counts': dict(event_counts),
            'unique_agents': len(self.agent_timeline),
            'unique_rooms': len(self.room_timeline),
            'message_chains': len(self.message_chains),
            'room_hierarchies': len([v for v in self.room_lineage.values() if v]),
            'first_event_time': self.events[0].get('timestamp') if self.events else None,
            'last_event_time': self.events[-1].get('timestamp') if self.events else None,
        }

    def get_agent_interactions(self, agent1_id: str, agent2_id: str) -> List[Dict[str, Any]]:
        """
        Get all interactions between two agents.

        Args:
            agent1_id: First agent ID
            agent2_id: Second agent ID

        Returns:
            List of events involving both agents
        """
        interactions = []
        for event in self.events:
            # Check if both agents are involved in this event
            event_agents = set()

            if event.get('agent_id') in [agent1_id, agent2_id]:
                event_agents.add(event.get('agent_id'))

            if event.get('sender_id') in [agent1_id, agent2_id]:
                event_agents.add(event.get('sender_id'))

            # Check participants for room events
            if event.get('event_type') == 'room_created':
                participants = event.get('participants', [])
                event_agents.update(p for p in participants if p in [agent1_id, agent2_id])

            if len(event_agents) >= 2:
                interactions.append(event)

        return interactions

    def detect_anomalies(self) -> List[Dict[str, Any]]:
        """
        Detect potential anomalies in the event timeline.

        Returns:
            List of detected anomalies with descriptions
        """
        anomalies = []

        # Detect slow responses (>5 seconds)
        for event in self.events:
            if event.get('event_type') == 'message_received':
                response_time = event.get('response_time_ms', 0) / 1000
                if response_time > 5:
                    anomalies.append({
                        'type': 'slow_response',
                        'severity': 'warning',
                        'message': f"Slow response: {response_time:.1f}s",
                        'event': event,
                    })

        # Detect failed API calls
        for event in self.events:
            if event.get('event_type') == 'api_call' and not event.get('success'):
                anomalies.append({
                    'type': 'api_failure',
                    'severity': 'error',
                    'message': f"API call failed: {event.get('endpoint')}",
                    'event': event,
                })

        # Detect orphaned rooms (created but no messages)
        for room_id in self.room_timeline:
            room_events = self.room_timeline[room_id]
            has_messages = any(
                e.get('event_type') in ['message_sent', 'message_received']
                for e in room_events
            )
            if not has_messages:
                anomalies.append({
                    'type': 'orphaned_room',
                    'severity': 'warning',
                    'message': f"Room created but no messages: {room_id}",
                    'event': room_events[0] if room_events else None,
                })

        return anomalies
