"""Tests for simulator commands and verbose trace rendering."""

from io import StringIO
from typing import Any

import agent
import simulate_chat


def test_phone_and_quit_commands() -> None:
    """Simulator commands switch identity and stop without invoking Gemini."""
    assert simulate_chat.parse_command("/phone 2020", "2010") == (
        "2020",
        True,
        "Switched to customer 2020.",
    )
    assert simulate_chat.parse_command("/quit", "2010") == ("2010", False, "Goodbye.")


def test_reset_command_and_verbose_trace(monkeypatch: Any) -> None:
    """Reset clears the selected session and verbose mode prints call data."""
    reset_phone: list[str] = []
    monkeypatch.setattr(agent, "reset_session", reset_phone.append)
    assert simulate_chat.parse_command("/reset", "2010") == (
        "2010",
        True,
        "Reset the session for 2010.",
    )
    assert reset_phone == ["2010"]

    monkeypatch.setattr(
        agent,
        "get_last_tool_calls",
        lambda phone: [
            {
                "tool": "search_products",
                "arguments": {"keyword": "mouse"},
                "result": {"success": True},
            }
        ],
    )
    output = StringIO()
    simulate_chat.print_tool_trace("2010", output)
    assert "search_products" in output.getvalue()
    assert "mouse" in output.getvalue()
