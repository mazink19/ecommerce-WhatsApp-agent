"""Unit tests for per-customer Gemini session behavior."""

from typing import Any

import agent


class FakeChat:
    """Simple chat stand-in returning deterministic reply text."""

    def __init__(self, reply: str = "Grounded reply") -> None:
        self.reply = reply
        self.messages: list[str] = []

    def send_message(self, text: str) -> Any:
        """Capture input and expose a Gemini-like text response."""
        self.messages.append(text)
        return type("Response", (), {"text": self.reply})()


class FakeChats:
    """Factory collection mirroring the Gemini chats API."""

    def __init__(self) -> None:
        self.created: list[tuple[str, Any, FakeChat]] = []

    def create(self, model: str, config: Any) -> FakeChat:
        """Create and retain an isolated fake chat."""
        chat = FakeChat()
        self.created.append((model, config, chat))
        return chat


class FakeClient:
    """Gemini client replacement for session tests."""

    def __init__(self) -> None:
        self.chats = FakeChats()


def setup_fake_client(monkeypatch: Any) -> FakeClient:
    """Reset state and install a fake Gemini client."""
    fake = FakeClient()
    monkeypatch.setattr(agent, "_client", fake)
    agent.sessions_customer.clear()
    agent._session_turns.clear()
    agent._last_tool_calls.clear()
    return fake


def test_sessions_are_isolated_per_phone(monkeypatch: Any) -> None:
    """Two phones produce two different chat objects and system identities."""
    fake = setup_fake_client(monkeypatch)
    first = agent.get_session("2010")
    second = agent.get_session("2020")
    assert first is not second
    assert len(fake.chats.created) == 2
    first_prompt = fake.chats.created[0][1].system_instruction
    second_prompt = fake.chats.created[1][1].system_instruction
    assert "2010" in first_prompt and "2020" in second_prompt


def test_customer_name_wrapper_always_overrides_model_value() -> None:
    """A model cannot choose another customer's cart identity."""
    received: dict[str, Any] = {}

    def cart_tool(customer_name: str, product_id: int) -> dict[str, Any]:
        """Record the supplied customer for test purposes.

        Args:
            customer_name: Customer ID.
            product_id: Product ID.

        Returns:
            A success value.
        """
        received.update(customer_name=customer_name, product_id=product_id)
        return {"success": True}

    wrapped = agent.bind_customer_tool(cart_tool, "locked-phone")
    assert wrapped(customer_name="attacker-phone", product_id=3) == {"success": True}
    assert received == {"customer_name": "locked-phone", "product_id": 3}
    assert wrapped.__name__ == "cart_tool"


def test_handle_message_uses_phone_session(monkeypatch: Any) -> None:
    """The public message handler returns chat text and remembers the customer session."""
    setup_fake_client(monkeypatch)
    assert agent.handle_message("2010", "show keyboards") == "Grounded reply"
    assert agent.sessions_customer["2010"].messages == ["show keyboards"]
