"""
Narrative Formatter - Human and LLM-readable log output.

This formatter creates story-like logs that are easy for humans and LLMs
to understand, making it simple to analyze test behavior.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from colorama import Fore, Style, init

# Initialize colorama for cross-platform color support
init(autoreset=True)


class NarrativeFormatter:
    """
    Generates narrative-style logs optimized for human and LLM readability.
    """

    def __init__(self, file_path: str, use_colors: bool = True):
        """
        Initialize narrative formatter.

        Args:
            file_path: Path to write narrative log
            use_colors: Whether to use ANSI colors (disable for file output)
        """
        self.file_path = file_path
        self.use_colors = use_colors
        self.start_time: Optional[float] = None
        self.file_handle = None

    def __enter__(self):
        """Context manager entry."""
        self.file_handle = open(self.file_path, 'w', encoding='utf-8')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.file_handle:
            self.file_handle.close()

    def _write(self, text: str):
        """Write text to file (without colors) and optionally to stdout."""
        # Strip color codes for file output
        clean_text = text
        if not self.use_colors:
            # Remove ANSI codes
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_text = ansi_escape.sub('', text)

        if self.file_handle:
            self.file_handle.write(clean_text + '\n')
            self.file_handle.flush()

    def _format_timestamp(self, timestamp: Optional[float] = None) -> str:
        """Format timestamp as readable time."""
        if timestamp is None:
            timestamp = time.time()
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        else:
            mins = int(seconds // 60)
            secs = seconds % 60
            return f"{mins}m {secs:.1f}s"

    def _relative_time(self) -> str:
        """Get relative time since test start."""
        if self.start_time is None:
            return "+0.0s"
        elapsed = time.time() - self.start_time
        return f"+{elapsed:.1f}s"

    def log_session_start(self, session_id: str, python_version: str, pytest_version: str):
        """Log test session start."""
        self.start_time = time.time()
        self._write("═" * 70)
        self._write(f"{Fore.CYAN}🧪 TEST SESSION STARTED{Style.RESET_ALL}")
        self._write(f"Session ID: {session_id}")
        self._write(f"Start Time: {self._format_timestamp()}")
        self._write(f"Python: {python_version}")
        self._write(f"Pytest: {pytest_version}")
        self._write("═" * 70)
        self._write("")

    def log_test_start(self, test_name: str, description: str, expected_behaviors: List[str]):
        """Log individual test start."""
        self.start_time = time.time()  # Reset for this test
        self._write(f"{Fore.BLUE}📝 TEST STARTED:{Style.RESET_ALL} {test_name}")
        self._write(f"Description: {description}")
        if expected_behaviors:
            self._write("Expected Behavior:")
            for i, behavior in enumerate(expected_behaviors, 1):
                self._write(f"  {i}. {behavior}")
        self._write(f"Time: {self._format_timestamp()}")
        self._write("")

    def log_setup_phase(self):
        """Log setup phase header."""
        self._write("─" * 70)
        self._write(f"{Fore.YELLOW}🔧 SETUP PHASE{Style.RESET_ALL}")
        self._write("─" * 70)
        self._write("")

    def log_agent_loaded(self, agent_name: str, agent_id: str):
        """Log agent configuration loaded."""
        self._write(f"🤖 Loading agent: {Fore.GREEN}{agent_name}{Style.RESET_ALL} ({agent_id})")

    def log_execution_phase(self):
        """Log execution phase header."""
        self._write("─" * 70)
        self._write(f"{Fore.YELLOW}🧪 TEST EXECUTION{Style.RESET_ALL}")
        self._write("─" * 70)
        self._write("")

    def log_api_call(self, method: str, endpoint: str, request: Dict[str, Any],
                     response: Dict[str, Any], duration: float, status: int):
        """Log API call details."""
        rel_time = self._relative_time()
        success = status >= 200 and status < 300
        status_color = Fore.GREEN if success else Fore.RED
        status_symbol = "✅" if success else "❌"

        self._write(f"{Fore.CYAN}🌐 [{rel_time}] API CALL:{Style.RESET_ALL} {method} {endpoint}")
        self._write("Request:")
        for key, value in request.items():
            self._write(f"  - {key}: {self._format_value(value)}")
        self._write("Response:")
        self._write(f"  {status_symbol} Status: {status_color}{status}{Style.RESET_ALL}")
        for key, value in response.items():
            self._write(f"  - {key}: {self._format_value(value)}")
        self._write(f"Duration: {self._format_duration(duration)}")
        self._write("")

    def log_message_sent(self, room_id: str, sender_id: str, sender_type: str,
                         content: str, message_id: str):
        """Log message sent."""
        rel_time = self._relative_time()
        self._write(f"{Fore.MAGENTA}💬 [{rel_time}] MESSAGE SENT:{Style.RESET_ALL} {room_id}")
        self._write(f"From: {sender_id} ({sender_type})")
        self._write(f'Content: "{content}"')
        self._write(f"Message ID: {message_id}")
        self._write("")

    def log_waiting_for_response(self, timeout: int):
        """Log waiting for response."""
        self._write(f"⏳ Waiting for agent response (timeout: {timeout}s)...")
        self._write("")

    def log_message_received(self, room_id: str, sender_id: str, sender_type: str,
                            content: str, message_id: str, response_time: float):
        """Log message received."""
        rel_time = self._relative_time()

        # Warn if response time is slow
        warning = ""
        if response_time > 5:
            warning = f" {Fore.RED}⚠️ (slow response!){Style.RESET_ALL}"
        elif response_time > 2:
            warning = f" {Fore.YELLOW}⚠️ (expected <2s){Style.RESET_ALL}"
        else:
            warning = f" {Fore.GREEN}✅{Style.RESET_ALL}"

        self._write(f"{Fore.MAGENTA}💬 [{rel_time}] MESSAGE RECEIVED:{Style.RESET_ALL} {room_id}")
        self._write(f"From: {sender_id} ({sender_type})")
        self._write(f'Content: "{content}"')
        self._write(f"Message ID: {message_id}")
        self._write(f"Response Time: {self._format_duration(response_time)}{warning}")
        self._write("")

    def log_agent_decision(self, agent_id: str, decision: str, reasoning: str,
                          analysis: Dict[str, Any]):
        """Log agent decision-making process."""
        rel_time = self._relative_time()
        self._write(f"{Fore.BLUE}🤖 [{rel_time}] AGENT DECISION:{Style.RESET_ALL} {agent_id}")
        self._write(f"Decision: {decision}")
        self._write(f"Reasoning: {reasoning}")
        if analysis:
            self._write("Analysis:")
            for key, value in analysis.items():
                self._write(f"  - {key}: {self._format_value(value)}")
        self._write("")

    def log_agent_processing(self, agent_id: str, action: str, input_data: Any,
                            processing_time: float, result: Any):
        """Log agent processing action."""
        rel_time = self._relative_time()
        self._write(f"{Fore.BLUE}🤖 [{rel_time}] AGENT PROCESSING:{Style.RESET_ALL} {agent_id}")
        self._write(f"Action: {action}")
        self._write(f"Input: {self._format_value(input_data)}")
        self._write(f"Processing time: {self._format_duration(processing_time)}")
        self._write(f"Result: {self._format_value(result)}")
        self._write("")

    def log_agent_synthesis(self, agent_id: str, action: str, inputs: List[Any],
                           description: str):
        """Log agent synthesis of multiple inputs."""
        rel_time = self._relative_time()
        self._write(f"{Fore.BLUE}🤖 [{rel_time}] AGENT SYNTHESIS:{Style.RESET_ALL} {agent_id}")
        self._write(f"Action: {action}")
        self._write(f"Input: {len(inputs)} specialist response(s)")
        self._write(f"{description}")
        self._write("")

    def log_assertion(self, assertion_type: str, expected: str, actual: str,
                     passed: bool, details: Optional[str] = None):
        """Log test assertion."""
        symbol = "✅" if passed else "❌"
        color = Fore.GREEN if passed else Fore.RED
        status = "PASSED" if passed else "FAILED"

        self._write(f"{color}{symbol} ASSERTION {status}:{Style.RESET_ALL} {assertion_type}")
        self._write(f"Expected: {expected}")
        self._write(f"Actual: {actual} {'✓' if passed else '✗'}")
        if details:
            self._write(f"Details: {details}")
        self._write("")

    def log_validation_summary(self, behaviors: List[Dict[str, Any]], metrics: Dict[str, Any],
                              warnings: List[str]):
        """Log test validation summary."""
        self._write("─" * 70)
        self._write(f"{Fore.CYAN}🔍 TEST VALIDATION SUMMARY{Style.RESET_ALL}")
        self._write("─" * 70)
        self._write("")

        self._write(f"{Fore.GREEN}✅ All expected behaviors observed:{Style.RESET_ALL}")
        for i, behavior in enumerate(behaviors, 1):
            status = "✅" if behavior.get('observed') else "❌"
            time_info = f" ({behavior.get('time', 'N/A')})" if behavior.get('time') else ""
            self._write(f"  {i}. {status} {behavior['description']}{time_info}")
        self._write("")

        self._write("📊 Metrics:")
        for key, value in metrics.items():
            self._write(f"  - {key}: {value}")
        self._write("")

        if warnings:
            self._write(f"{Fore.YELLOW}⚠️ Warnings:{Style.RESET_ALL}")
            for warning in warnings:
                self._write(f"  - {warning}")
            self._write("")

    def log_test_end(self, test_name: str, status: str, duration: float,
                     summary: Dict[str, Any]):
        """Log test completion."""
        passed = status.lower() == "passed"
        symbol = "✅" if passed else "❌"
        color = Fore.GREEN if passed else Fore.RED

        self._write("─" * 70)
        self._write(f"{color}📊 TEST COMPLETED{Style.RESET_ALL}")
        self._write(f"Status: {symbol} {status.upper()}")
        self._write(f"Duration: {self._format_duration(duration)}")
        self._write("═" * 70)
        self._write("")

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if isinstance(value, str):
            if len(value) > 100:
                return f'"{value[:100]}..."'
            return f'"{value}"'
        elif isinstance(value, (list, tuple)):
            if len(value) > 3:
                return f"[{', '.join(map(str, value[:3]))}, ... ({len(value)} total)]"
            return str(value)
        elif isinstance(value, dict):
            if len(value) > 3:
                keys = list(value.keys())[:3]
                return f"{{{', '.join(f'{k}: ...' for k in keys)}, ... ({len(value)} keys)}}"
            return str(value)
        else:
            return str(value)
