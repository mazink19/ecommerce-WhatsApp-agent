"""Unit tests for per-customer Gemini session behavior."""

import json
from collections import defaultdict
from typing import Any

import pytest

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
    monkeypatch.setenv("AI_PROVIDER", "gemini")
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
    sent_message = agent.sessions_customer["2010"].messages[0]
    assert "Reply in English" in sent_message
    assert "show keyboards" in sent_message


def test_explicit_quantity_guard_prevents_silent_reduction() -> None:
    """A tool call cannot lower a clear single-item customer quantity without reporting it."""
    agent._single_requested_quantity["2010"] = 99

    def add_item_to_cart(
        customer_name: str, product_id: int, quantity: int = 1
    ) -> dict[str, Any]:
        """Pretend to add a product.

        Args:
            customer_name: Customer ID.
            product_id: Product ID.
            quantity: Product quantity.

        Returns:
            A success value.
        """
        return {"success": True}

    guarded = agent.bind_customer_tool(add_item_to_cart, "2010")
    result = guarded(customer_name="2010", product_id=1, quantity=11)
    assert result["success"] is False
    assert "requested 99" in result["error"]
    agent._single_requested_quantity.pop("2010", None)


def test_explicit_single_quantity_supports_arabic_digits() -> None:
    """The guard recognizes Arabic numerals but avoids compound product quantities."""
    assert agent._explicit_single_quantity("أضف ٩ كيبورد") == 9
    assert agent._explicit_single_quantity("add 2 keyboard and 3 mouse") is None


def test_latest_message_language_detection():
    """Latest message dominant language can override prior conversation language."""
    assert agent.detect_language("What is the price?") == "English"
    assert agent.detect_language("كم السعر؟") == "Arabic"
    assert agent.detect_language("price السعر") == "English"


def test_ambiguous_mouse_is_clarified_and_choice_resumes(monkeypatch: Any) -> None:
    """An unspecified mouse is not acted on and a later model selection resumes normally."""
    setup_fake_client(monkeypatch)
    first = agent.handle_message("mouse-test", "I want a mouse")
    assert "Which mouse" in first
    assert "mouse-test" not in agent.sessions_customer

    second = agent.handle_message("mouse-test", "Logitech MX Master 3S")
    assert second == "Grounded reply"
    assert len(agent.sessions_customer["mouse-test"].messages) == 1
    sent_message = agent.sessions_customer["mouse-test"].messages[0]
    assert "Reply in English" in sent_message
    assert (
        "Find and add the customer's clarified mouse choice: Logitech MX Master 3S"
        in sent_message
    )


def test_specific_mouse_does_not_trigger_clarification():
    """A fully specified product request continues to the normal agent workflow."""
    assert not agent._is_ambiguous_mouse_request("Add Logitech MX Master 3S to my cart")


def test_groq_request_includes_latest_language_directive(monkeypatch: Any) -> None:
    """Groq API messages carry a per-turn language instruction independent of history."""
    captured: list[dict[str, Any]] = []

    class Completions:
        def create(self, **kwargs: Any) -> Any:
            captured.extend(kwargs["messages"][-2:])
            message = type(
                "Message",
                (),
                {
                    "content": "Here you go",
                    "tool_calls": None,
                    "model_dump": lambda self, **k: {
                        "role": "assistant",
                        "content": self.content,
                    },
                },
            )()
            return type(
                "Response",
                (),
                {"choices": [type("Choice", (), {"message": message})()]},
            )()

    client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    session = agent.GroqChatSession("p", client, "test-model", [])
    session.send_message("What is the price?")
    assert captured[0]["role"] == "system"
    assert "English" in captured[0]["content"]


def test_groq_deduplicates_identical_tool_calls() -> None:
    """A repeated identical call is acknowledged with its result and executes once."""
    executions: list[int] = []

    def search_products(keyword: str) -> dict[str, Any]:
        """Search for a product.

        Args:
            keyword: Product search term.

        Returns:
            A search result.
        """
        executions.append(1)
        return {"success": True, "data": []}

    call = type(
        "ToolCall",
        (),
        {
            "id": "c1",
            "function": type(
                "Function",
                (),
                {"name": "search_products", "arguments": '{"keyword":"mouse"}'},
            )(),
        },
    )()
    assistant = type(
        "Message",
        (),
        {
            "tool_calls": [call],
            "content": None,
            "model_dump": lambda self, **kwargs: {
                "role": "assistant",
                "tool_calls": [],
            },
        },
    )()
    final = type(
        "Message",
        (),
        {
            "tool_calls": None,
            "content": "No matching product.",
            "model_dump": lambda self, **kwargs: {
                "role": "assistant",
                "content": self.content,
            },
        },
    )()

    class Completions:
        count = 0

        def create(self, **kwargs: Any) -> Any:
            self.count += 1
            message = assistant if self.count <= 2 else final
            return type(
                "Response",
                (),
                {"choices": [type("Choice", (), {"message": message})()]},
            )()

    client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    session = agent.GroqChatSession("p", client, "test-model", [search_products])
    result = session.send_message("Find a mouse")
    assert result.text == "No matching product."
    assert len(executions) == 1


def test_groq_enforces_configured_tool_call_limit(monkeypatch: Any) -> None:
    """The model cannot execute more unique tool actions than the configured cap."""
    monkeypatch.setenv("MAX_TOOL_CALLS_PER_TURN", "1")
    executions: list[str] = []

    def search_products(keyword: str) -> dict[str, Any]:
        """Search the catalog.

        Args:
            keyword: Search term.

        Returns:
            Search data.
        """
        executions.append(keyword)
        return {"success": True}

    calls = [
        type(
            "ToolCall",
            (),
            {
                "id": str(i),
                "function": type(
                    "Function",
                    (),
                    {
                        "name": "search_products",
                        "arguments": json.dumps({"keyword": f"term{i}"}),
                    },
                )(),
            },
        )()
        for i in range(2)
    ]
    messages = [
        type(
            "Message",
            (),
            {
                "tool_calls": [call],
                "content": None,
                "model_dump": lambda self, **kwargs: {
                    "role": "assistant",
                    "tool_calls": [],
                },
            },
        )()
        for call in calls
    ]
    final = type(
        "Message",
        (),
        {
            "tool_calls": None,
            "content": "Stopped safely.",
            "model_dump": lambda self, **kwargs: {
                "role": "assistant",
                "content": self.content,
            },
        },
    )()

    class Completions:
        index = 0

        def create(self, **kwargs: Any) -> Any:
            message = messages[self.index] if self.index < len(messages) else final
            self.index += 1
            return type(
                "Response",
                (),
                {"choices": [type("Choice", (), {"message": message})()]},
            )()

    client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    session = agent.GroqChatSession("p", client, "test-model", [search_products])
    with pytest.raises(RuntimeError, match="configured tool-call limit"):
        session.send_message("Find something")
    assert executions == ["term0"]


def test_groq_tool_failure_is_returned_as_failure_data() -> None:
    """Tool exceptions are safely represented to the model without leaking exception contents."""

    def search_products(keyword: str) -> dict[str, Any]:
        """Search.

        Args:
            keyword: Term.

        Returns:
            Data.
        """
        raise RuntimeError("sensitive internal details")

    call = type(
        "ToolCall",
        (),
        {
            "id": "failure",
            "function": type(
                "Function",
                (),
                {"name": "search_products", "arguments": '{"keyword":"x"}'},
            )(),
        },
    )()
    messages = [
        type(
            "Message",
            (),
            {
                "tool_calls": [call],
                "content": None,
                "model_dump": lambda self, **kwargs: {
                    "role": "assistant",
                    "tool_calls": [],
                },
            },
        )(),
        type(
            "Message",
            (),
            {
                "tool_calls": None,
                "content": "Search failed.",
                "model_dump": lambda self, **kwargs: {
                    "role": "assistant",
                    "content": self.content,
                },
            },
        )(),
    ]

    class Completions:
        index = 0

        def create(self, **kwargs: Any) -> Any:
            message = messages[self.index]
            self.index += 1
            return type(
                "Response",
                (),
                {"choices": [type("Choice", (), {"message": message})()]},
            )()

    client = type(
        "Client", (), {"chat": type("Chat", (), {"completions": Completions()})()}
    )()
    session = agent.GroqChatSession("p", client, "test-model", [search_products])
    session.send_message("Search")
    tool_result = json.loads(session.messages[-2]["content"])
    assert tool_result == {
        "success": False,
        "error": "Tool call failed (RuntimeError).",
    }


@pytest.mark.parametrize("requested", [2, 5])
def test_add_quantity_within_stock_proceeds(monkeypatch: Any, requested: int) -> None:
    """Quantities at or below verified stock add exactly the requested amount."""
    monkeypatch.setattr(
        agent, "_single_requested_quantity", defaultdict(lambda: requested)
    )
    added: list[int] = []
    agent._turn_additions["quantity-test"] = {}
    fake_tools = list(agent.ALL_TOOLS)
    fake_tools[2] = lambda product_id: {"success": True, "name": "Mouse", "stock": 5}
    fake_tools[4] = lambda customer_name, product_id, quantity: (
        added.append(quantity) or {"success": True}
    )
    fake_tools[4].__name__ = "add_item_to_cart"
    monkeypatch.setattr(agent, "ALL_TOOLS", fake_tools)
    wrapped = agent.bind_customer_tool(fake_tools[4], "quantity-test")
    assert (
        wrapped(customer_name="ignored", product_id=7, quantity=requested)["success"]
        is True
    )
    assert added == [requested]


def test_excess_quantity_requires_approval_and_rechecks_stock(monkeypatch: Any) -> None:
    """Excess requests do not mutate cart, then explicit approval rechecks stock before adding."""
    stock = {"value": 4}
    added: list[int] = []
    agent._turn_additions["quantity-test"] = {}
    monkeypatch.setattr(agent, "_single_requested_quantity", defaultdict(lambda: 12))
    fake_tools = list(agent.ALL_TOOLS)
    fake_tools[2] = lambda product_id: {
        "success": True,
        "name": "Mouse",
        "stock": stock["value"],
    }
    fake_tools[4] = lambda customer_name, product_id, quantity: (
        added.append(quantity) or {"success": True}
    )
    fake_tools[4].__name__ = "add_item_to_cart"
    monkeypatch.setattr(agent, "ALL_TOOLS", fake_tools)
    wrapped = agent.bind_customer_tool(fake_tools[4], "quantity-test")
    result = wrapped(customer_name="ignored", product_id=7, quantity=12)
    assert result["success"] is False
    assert added == []
    assert agent._pending_quantity["quantity-test"]["available"] == 4

    stock["value"] = 2
    response = agent._approve_pending_quantity("quantity-test")
    assert "Stock changed" in response
    assert added == []
    assert agent._pending_quantity["quantity-test"]["available"] == 2

    response = agent._approve_pending_quantity("quantity-test")
    assert "Added 2" in response
    assert added == [2]


def test_quantity_reject_does_not_add(monkeypatch: Any) -> None:
    """A no response clears pending quantity without a cart action."""
    agent._pending_quantity["quantity-no"] = {
        "product_id": 7,
        "product_name": "Mouse",
        "requested": 12,
        "available": 4,
    }
    agent._last_tool_calls["quantity-no"] = []
    assert (
        agent.handle_message("quantity-no", "no")
        == "Understood. I did not add anything."
    )
    assert "quantity-no" not in agent._pending_quantity
    assert agent.get_last_tool_calls("quantity-no") == []


def test_system_prompt_enforces_store_scope_and_current_turn_freshness() -> None:
    """Governance prompt rejects off-topic requests and stale catalog facts."""
    prompt = agent.build_system_prompt("customer-1")
    assert "THIS turn" in prompt
    assert "A result from an earlier turn is stale" in prompt
    assert "You are a store sales assistant only" in prompt
    assert "politely say you can only help with store matters" in prompt
    assert "LATEST customer message" in prompt
    assert "WhatsApp *bold*" in prompt


def test_gemini_receives_latest_turn_language_instruction(monkeypatch: Any) -> None:
    """Gemini receives an explicit language directive on every individual turn."""
    setup_fake_client(monkeypatch)
    agent.handle_message("language-test", "كم سعر الكيبورد؟")
    sent = agent.sessions_customer["language-test"].messages[-1]
    assert "Reply in Arabic" in sent
    assert "never reuse old data" in sent


def test_price_answer_is_blocked_without_current_turn_catalog_tool(
    monkeypatch: Any,
) -> None:
    """A model cannot return a price if no successful catalog tool ran this turn."""
    setup_fake_client(monkeypatch)
    response = agent.handle_message("price-test", "What is the price of the keyboard?")
    assert response == agent._localized_verification_fallback(
        "What is the price of the keyboard?"
    )
    assert "Grounded reply" not in response


def test_current_turn_catalog_check_requires_successful_tool_result() -> None:
    """Only a successful current-turn catalog lookup satisfies price/stock governance."""
    agent._last_tool_calls["catalog-test"] = [
        {"tool": "get_product_details", "result": {"success": False}}
    ]
    assert not agent._has_current_catalog_check("catalog-test")
    agent._last_tool_calls["catalog-test"] = [
        {
            "tool": "get_product_details",
            "result": {"success": True, "data": {"price": 10}},
        }
    ]
    assert agent._has_current_catalog_check("catalog-test")
