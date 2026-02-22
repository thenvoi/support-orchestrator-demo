"""
Test Logger - Main logging orchestrator.

This is the primary interface for test logging. It coordinates the narrative
formatter, structured formatter, and event tracker to provide comprehensive
test observability.
"""

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from .narrative_formatter import NarrativeFormatter
from .structured_formatter import StructuredFormatter
from .event_tracker import EventTracker


class TestLogger:
    """
    Main logging orchestrator that coordinates all logging components.
    """

    def __init__(self, log_dir: Optional[str] = None, use_colors: bool = True):
        """
        Initialize test logger.

        Args:
            log_dir: Directory to write logs (default: logs/test_run_<timestamp>/)
            use_colors: Whether to use colors in narrative logs
        """
        # Create log directory
        if log_dir is None:
            timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
            log_dir = f"logs/test_run_{timestamp}"

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create symlink to latest
        latest_link = self.log_dir.parent / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        try:
            latest_link.symlink_to(self.log_dir.name, target_is_directory=True)
        except OSError:
            pass  # Symlink creation may fail on some systems

        # Initialize formatters
        self.narrative = NarrativeFormatter(
            str(self.log_dir / "narrative.log"),
            use_colors=use_colors
        )
        self.structured = StructuredFormatter(
            str(self.log_dir / "structured.jsonl")
        )
        self.tracker = EventTracker()

        self.session_id: Optional[str] = None
        self.test_id: Optional[str] = None
        self.test_start_time: Optional[float] = None

        # Context managers
        self._context_active = False

    def __enter__(self):
        """Context manager entry."""
        self.narrative.__enter__()
        self.structured.__enter__()
        self._context_active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type:
            # Log the exception
            self.log_error(
                error_type=exc_type.__name__,
                message=str(exc_val),
                stack_trace=str(exc_tb) if exc_tb else None,
            )

        # Write summary
        self._write_summary()

        self.narrative.__exit__(exc_type, exc_val, exc_tb)
        self.structured.__exit__(exc_type, exc_val, exc_tb)
        self._context_active = False

    def _write_summary(self):
        """Write summary.md file with test results."""
        summary_path = self.log_dir / "summary.md"

        timeline = self.tracker.get_timeline_summary()
        anomalies = self.tracker.detect_anomalies()

        with open(summary_path, 'w') as f:
            f.write(f"# Test Run Summary\n\n")
            f.write(f"**Session ID:** {self.session_id}\n")
            f.write(f"**Log Directory:** `{self.log_dir}`\n")
            f.write(f"**Start Time:** {timeline.get('first_event_time', 'N/A')}\n")
            f.write(f"**End Time:** {timeline.get('last_event_time', 'N/A')}\n\n")

            f.write(f"## Timeline Statistics\n\n")
            f.write(f"- Total Events: {timeline['total_events']}\n")
            f.write(f"- Unique Agents: {timeline['unique_agents']}\n")
            f.write(f"- Unique Rooms: {timeline['unique_rooms']}\n")
            f.write(f"- Message Chains: {timeline['message_chains']}\n\n")

            f.write(f"## Event Breakdown\n\n")
            for event_type, count in timeline['event_counts'].items():
                f.write(f"- {event_type}: {count}\n")

            if anomalies:
                f.write(f"\n## Anomalies Detected\n\n")
                for anomaly in anomalies:
                    severity = anomaly['severity'].upper()
                    f.write(f"- **[{severity}]** {anomaly['message']}\n")

            f.write(f"\n## Files\n\n")
            f.write(f"- `narrative.log` - Human-readable test narrative\n")
            f.write(f"- `structured.jsonl` - Machine-readable JSON Lines log\n")
            f.write(f"- `summary.md` - This file\n")

    # Session-level logging

    def log_session_start(self, python_version: str = None, pytest_version: str = None):
        """Log test session start."""
        self.session_id = str(uuid.uuid4())[:8]

        if python_version is None:
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        if pytest_version is None:
            try:
                import pytest
                pytest_version = pytest.__version__
            except:
                pytest_version = "unknown"

        self.narrative.log_session_start(self.session_id, python_version, pytest_version)
        self.structured.log_session_start(self.session_id, python_version, pytest_version)

    # Test-level logging

    def log_test_start(self, test_name: str, description: str = "",
                      expected_behaviors: Optional[List[str]] = None):
        """Log individual test start."""
        self.test_id = str(uuid.uuid4())[:8]
        self.test_start_time = time.time()

        expected_behaviors = expected_behaviors or []

        self.narrative.log_test_start(test_name, description, expected_behaviors)
        self.structured.log_test_start(test_name, self.test_id, description, expected_behaviors)

        event = {
            'event_type': 'test_start',
            'test_name': test_name,
            'test_id': self.test_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    def log_setup_phase(self):
        """Log setup phase header."""
        self.narrative.log_setup_phase()

    def log_execution_phase(self):
        """Log execution phase header."""
        self.narrative.log_execution_phase()

    def log_test_end(self, test_name: str, status: str, summary: Optional[Dict[str, Any]] = None):
        """Log test completion."""
        duration = time.time() - self.test_start_time if self.test_start_time else 0
        summary = summary or {}

        self.narrative.log_test_end(test_name, status, duration, summary)
        self.structured.log_test_end(
            test_name=test_name,
            status=status,
            duration_s=duration,
            assertions_passed=summary.get('assertions_passed', 0),
            assertions_failed=summary.get('assertions_failed', 0),
            summary=summary
        )

        event = {
            'event_type': 'test_end',
            'test_name': test_name,
            'test_id': self.test_id,
            'status': status,
            'duration_s': duration,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

        self.test_id = None
        self.test_start_time = None

    # Agent logging

    def log_agent_loaded(self, agent_name: str, agent_id: str, config: Optional[Dict] = None):
        """Log agent configuration loaded."""
        config = config or {}
        self.narrative.log_agent_loaded(agent_name, agent_id)
        self.structured.log_agent_loaded(agent_name, agent_id, config)

        event = {
            'event_type': 'agent_loaded',
            'agent_name': agent_name,
            'agent_id': agent_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    def log_agent_decision(self, agent_id: str, decision: str, reasoning: str,
                          analysis: Optional[Dict[str, Any]] = None):
        """Log agent decision-making process."""
        analysis = analysis or {}
        self.narrative.log_agent_decision(agent_id, decision, reasoning, analysis)
        self.structured.log_agent_decision(agent_id, decision, reasoning, analysis)

        event = {
            'event_type': 'agent_decision',
            'agent_id': agent_id,
            'decision': decision,
            'reasoning': reasoning,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    def log_agent_processing(self, agent_id: str, action: str, input_data: Any,
                            processing_time: float, result: Any):
        """Log agent processing action."""
        self.narrative.log_agent_processing(agent_id, action, input_data, processing_time, result)
        self.structured.log_agent_processing(
            agent_id, action, input_data, processing_time * 1000, result
        )

        event = {
            'event_type': 'agent_processing',
            'agent_id': agent_id,
            'action': action,
            'processing_time_ms': processing_time * 1000,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    def log_agent_synthesis(self, agent_id: str, action: str, inputs: List[Any],
                           description: str):
        """Log agent synthesis of multiple inputs."""
        self.narrative.log_agent_synthesis(agent_id, action, inputs, description)

    # API logging

    def log_api_call(self, method: str, endpoint: str, request: Dict[str, Any],
                    response: Dict[str, Any], duration: float, status: int):
        """Log API call details."""
        self.narrative.log_api_call(method, endpoint, request, response, duration, status)
        self.structured.log_api_call(method, endpoint, request, response, duration * 1000, status)

        event = {
            'event_type': 'api_call',
            'method': method,
            'endpoint': endpoint,
            'duration_ms': duration * 1000,
            'status': status,
            'success': 200 <= status < 300,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    # Message logging

    def log_message_sent(self, room_id: str, sender_id: str, sender_type: str,
                        content: str, message_id: str, metadata: Optional[Dict] = None):
        """Log message sent."""
        self.narrative.log_message_sent(room_id, sender_id, sender_type, content, message_id)
        self.structured.log_message_sent(room_id, sender_id, sender_type, content, message_id, metadata)

        event = {
            'event_type': 'message_sent',
            'room_id': room_id,
            'sender_id': sender_id,
            'message_id': message_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    def log_waiting_for_response(self, timeout: int):
        """Log waiting for response."""
        self.narrative.log_waiting_for_response(timeout)

    def log_message_received(self, room_id: str, sender_id: str, sender_type: str,
                            content: str, message_id: str, response_time: float,
                            metadata: Optional[Dict] = None):
        """Log message received."""
        self.narrative.log_message_received(
            room_id, sender_id, sender_type, content, message_id, response_time
        )
        self.structured.log_message_received(
            room_id, sender_id, sender_type, content, message_id, response_time * 1000, metadata
        )

        event = {
            'event_type': 'message_received',
            'room_id': room_id,
            'sender_id': sender_id,
            'message_id': message_id,
            'response_time_ms': response_time * 1000,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    # Room logging

    def log_room_created(self, room_id: str, name: str, participants: List[str],
                        created_by: str, parent_room: Optional[str] = None):
        """Log room creation."""
        self.structured.log_room_created(room_id, name, participants, created_by, parent_room)

        event = {
            'event_type': 'room_created',
            'room_id': room_id,
            'name': name,
            'participants': participants,
            'created_by': created_by,
            'parent_room': parent_room,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    # Memory logging

    def log_memory_operation(self, agent_id: str, operation: str, key: str,
                            value: Any, scope: str, room_id: Optional[str] = None):
        """Log memory read/write operation."""
        self.structured.log_memory_operation(agent_id, operation, key, value, scope, room_id)

        event = {
            'event_type': 'memory_operation',
            'agent_id': agent_id,
            'operation': operation,
            'key': key,
            'scope': scope,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    # Assertion logging

    def log_assertion(self, assertion_type: str, expected: Any, actual: Any,
                     passed: bool, details: Optional[str] = None):
        """Log test assertion."""
        self.narrative.log_assertion(assertion_type, str(expected), str(actual), passed, details)
        self.structured.log_assertion(assertion_type, expected, actual, passed, details)

        event = {
            'event_type': 'assertion',
            'assertion_type': assertion_type,
            'passed': passed,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    # Error logging

    def log_error(self, error_type: str, message: str, stack_trace: Optional[str] = None,
                 context: Optional[Dict] = None):
        """Log error."""
        self.structured.log_error(error_type, message, stack_trace, context)

        event = {
            'event_type': 'error',
            'error_type': error_type,
            'message': message,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        self.tracker.add_event(event)

    # Summary logging

    def log_validation_summary(self, behaviors: List[Dict[str, Any]],
                              metrics: Dict[str, Any], warnings: List[str]):
        """Log test validation summary."""
        self.narrative.log_validation_summary(behaviors, metrics, warnings)

    # Utility methods

    def get_log_directory(self) -> Path:
        """Get the log directory path."""
        return self.log_dir

    def get_event_tracker(self) -> EventTracker:
        """Get the event tracker instance."""
        return self.tracker
