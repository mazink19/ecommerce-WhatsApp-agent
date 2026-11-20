"""Non-live governance tests for policy and graceful failure behavior."""

from typing import Any

import agent


def test_system_prompt_contains_required_governance_rules() -> None:
    """The session policy requires grounding, isolation, language, and checkout safeguards."""
    prompt = agent.build_system_prompt("2010")
    for required_text in (
        "2010",
        "never invent or guess",
        "explicitly asks to check out",
        "shipping address",
        "stock 0",
        "Never silently reduce",
        "in_stock_only=True",
        "customer's language",
        "*bold*",
    ):
        assert required_text in prompt


def test_fallback_errors_follow_customer_language() -> None:
    """An unavailable model returns a friendly localized response, not an exception."""
    assert "Sorry" in agent._friendly_error("show keyboards")
    assert "عذرًا" in agent._friendly_error("عايز كيبورد")


def test_message_handler_recovers_from_unavailable_model(monkeypatch: Any) -> None:
    """A Gemini failure never escapes the public message handler."""
    agent.reset_session("unavailable-test")

    def fail_get_session(phone: str) -> Any:
        """Raise a non-transient model error for test purposes."""
        raise RuntimeError("invalid model configuration")

    monkeypatch.setattr(agent, "get_session", fail_get_session)
    reply = agent.handle_message("unavailable-test", "show keyboards")
    assert "Sorry" in reply
