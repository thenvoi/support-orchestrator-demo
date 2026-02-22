"""
Structured Formatter - JSON Lines output for programmatic analysis.

This formatter creates machine-readable logs in JSON Lines format,
making it easy to parse, analyze, and process test data programmatically.
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


class StructuredFormatter:
    """
    Generates structured logs in JSON Lines format for machine processing.
    """

    def __init__(self, file_path: str):
        """
        Initialize structured formatter.

        Args:
            file_path: Path to write JSON Lines log
        """
        self.file_path = file_path
        self.file_handle = None
        self.session_id: Optional[str] = None
        self.test_id: Optional[str] = None

    def __enter__(self):
        """Context manager entry."""
        self.file_handle = open(self.file_path, 'w', encoding='utf-8')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.file_handle:
            self.file_handle.close()

    def _write_event(self, event: Dict[str, Any]):
        """Write a single event as JSON line."""
        # Add common fields
        if 'timestamp' not in event:
            event['timestamp'] = datetime.utcnow().isoformat() + 'Z'

        if self.session_id and 'session_id' not in event:
            event['session_id'] = self.session_id

        if self.test_id and 'test_id' not in event:
            event['test_id'] = self.test_id

        if self.file_handle:
            json.dump(event, self.file_handle, default=str)
            self.file_handle.write('\n')
            self.file_handle.flush()

    def log_session_start(self, session_id: str, python_version: str, pytest_version: str):
        """Log test session start."""
        self.session_id = session_id
        self._write_event({
            'event_type': 'session_start',
            'session_id': session_id,
            'python_version': python_version,
            'pytest_version': pytest_version,
        })

    def log_test_start(self, test_name: str, test_id: str, description: str,
                      expected_behaviors: List[str]):
        """Log individual test start."""
        self.test_id = test_id
        self._write_event({
            'event_type': 'test_start',
            'test_name': test_name,
            'test_id': test_id,
            'description': description,
            'expected_behaviors': expected_behaviors,
        })

    def log_agent_loaded(self, agent_name: str, agent_id: str, config: Dict[str, Any]):
        """Log agent configuration loaded."""
        self._write_event({
            'event_type': 'agent_loaded',
            'agent_name': agent_name,
            'agent_id': agent_id,
            'config': config,
        })

    def log_api_call(self, method: str, endpoint: str, request: Dict[str, Any],
                    response: Dict[str, Any], duration_ms: float, status: int):
        """Log API call details."""
        self._write_event({
            'event_type': 'api_call',
            'method': method,
            'endpoint': endpoint,
            'request': request,
            'response': response,
            'duration_ms': duration_ms,
            'status': status,
            'success': 200 <= status < 300,
        })

    def log_message_sent(self, room_id: str, sender_id: str, sender_type: str,
                        content: str, message_id: str, metadata: Optional[Dict] = None):
        """Log message sent."""
        self._write_event({
            'event_type': 'message_sent',
            'room_id': room_id,
            'sender_id': sender_id,
            'sender_type': sender_type,
            'content': content,
            'message_id': message_id,
            'metadata': metadata or {},
        })

    def log_message_received(self, room_id: str, sender_id: str, sender_type: str,
                            content: str, message_id: str, response_time_ms: float,
                            metadata: Optional[Dict] = None):
        """Log message received."""
        self._write_event({
            'event_type': 'message_received',
            'room_id': room_id,
            'sender_id': sender_id,
            'sender_type': sender_type,
            'content': content,
            'message_id': message_id,
            'response_time_ms': response_time_ms,
            'metadata': metadata or {},
        })

    def log_agent_decision(self, agent_id: str, decision: str, reasoning: str,
                          analysis: Dict[str, Any], metadata: Optional[Dict] = None):
        """Log agent decision-making process."""
        self._write_event({
            'event_type': 'agent_decision',
            'agent_id': agent_id,
            'decision': decision,
            'reasoning': reasoning,
            'analysis': analysis,
            'metadata': metadata or {},
        })

    def log_agent_processing(self, agent_id: str, action: str, input_data: Any,
                            processing_time_ms: float, result: Any,
                            metadata: Optional[Dict] = None):
        """Log agent processing action."""
        self._write_event({
            'event_type': 'agent_processing',
            'agent_id': agent_id,
            'action': action,
            'input': input_data,
            'processing_time_ms': processing_time_ms,
            'result': result,
            'metadata': metadata or {},
        })

    def log_room_created(self, room_id: str, name: str, participants: List[str],
                        created_by: str, parent_room: Optional[str] = None):
        """Log room creation."""
        self._write_event({
            'event_type': 'room_created',
            'room_id': room_id,
            'name': name,
            'participants': participants,
            'created_by': created_by,
            'parent_room': parent_room,
        })

    def log_memory_operation(self, agent_id: str, operation: str, key: str,
                            value: Any, scope: str, room_id: Optional[str] = None):
        """Log memory read/write operation."""
        self._write_event({
            'event_type': 'memory_operation',
            'agent_id': agent_id,
            'operation': operation,  # 'read', 'write', 'delete'
            'key': key,
            'value': value,
            'scope': scope,  # 'room', 'user', 'global'
            'room_id': room_id,
        })

    def log_assertion(self, assertion_type: str, expected: Any, actual: Any,
                     passed: bool, details: Optional[str] = None):
        """Log test assertion."""
        self._write_event({
            'event_type': 'assertion',
            'assertion_type': assertion_type,
            'expected': expected,
            'actual': actual,
            'passed': passed,
            'details': details,
        })

    def log_error(self, error_type: str, message: str, stack_trace: Optional[str] = None,
                 context: Optional[Dict] = None):
        """Log error."""
        self._write_event({
            'event_type': 'error',
            'error_type': error_type,
            'message': message,
            'stack_trace': stack_trace,
            'context': context or {},
        })

    def log_test_end(self, test_name: str, status: str, duration_s: float,
                    assertions_passed: int, assertions_failed: int,
                    summary: Dict[str, Any]):
        """Log test completion."""
        self._write_event({
            'event_type': 'test_end',
            'test_name': test_name,
            'status': status,
            'duration_s': duration_s,
            'assertions_passed': assertions_passed,
            'assertions_failed': assertions_failed,
            'summary': summary,
        })
        # Clear test_id after test ends
        self.test_id = None

    def log_session_end(self, total_tests: int, passed: int, failed: int, skipped: int,
                       total_duration_s: float):
        """Log test session end."""
        self._write_event({
            'event_type': 'session_end',
            'total_tests': total_tests,
            'passed': passed,
            'failed': failed,
            'skipped': skipped,
            'total_duration_s': total_duration_s,
        })
