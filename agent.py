"""Gemini-powered, session-isolated sales assistant."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import ALL_TOOLS

load_dotenv()
LOGGER = logging.getLogger(__name__)
MAX_SESSION_TURNS = 40
sessions_customer: dict[str, Any] = {}
_session_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_session_guard = threading.Lock()
_session_turns: dict[str, int] = defaultdict(int)
_last_tool_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
_client: Any | None = None


def build_system_prompt(phone: str) -> str:
    """Build the non-negotiable store policy for one customer session."""
    store_name = os.getenv("STORE_NAME", "My Store")
    return f"""You are the concise sales assistant for {store_name}.
The customer's ID is `{phone}`. Always pass this exact value as `customer_name` for cart and checkout tools.

Ground every factual store claim in a relevant tool result from this turn or conversation: never invent or guess a price, stock level, cart contents, order status, product availability, order number, or total. If a tool fails, explain the failure honestly.
Handle compound requests completely in one turn. Search every requested item first, then add each selected item. Only check out when the customer explicitly asks to check out and has supplied a shipping address. Without an address, ask for it. If the customer has not explicitly requested checkout, confirm the cart instead.
The catalog product names are English. When an Arabic customer uses a transliterated name, search its likely English catalog term (for example, "كيبورد ميكانيكال" means "Mechanical Keyboard" and "ماوس جيمينج" means "Gaming Mouse") rather than searching the Arabic transliteration literally.
If an item is out of stock, say so and search in-stock alternatives in the same category. If the cart is empty, explain that and offer help rather than calling checkout.
Reply in the customer's language; Arabic dialects, including Egyptian, are welcome. Keep replies short and do not overuse emoji. Use WhatsApp *bold* for prices, product names, order numbers, and totals. Use EGP (ج.م) consistently."""


def bind_customer_tool(tool: Callable[..., dict[str, Any]], phone: str) -> Callable[..., dict[str, Any]]:
    """Return a schema-preserving tool wrapper that logs calls and pins cart identity."""
    import inspect

    signature = inspect.signature(tool)

    @wraps(tool)
    def bound_tool(*args: Any, **kwargs: Any) -> dict[str, Any]:
        bound = signature.bind_partial(*args, **kwargs)
        if "customer_name" in signature.parameters:
            bound.arguments["customer_name"] = phone
        result = tool(*bound.args, **bound.kwargs)
        _last_tool_calls[phone].append(
            {"tool": tool.__name__, "arguments": dict(bound.arguments), "result": result}
        )
        return result

    return bound_tool


def _session_tools(phone: str) -> list[Callable[..., dict[str, Any]]]:
    """Bind all identity-sensitive functions to a session's phone."""
    return [bind_customer_tool(tool, phone) for tool in ALL_TOOLS]


def _get_client() -> Any:
    """Create the Gemini client lazily so local tests do not require a secret."""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        _client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"},
        )
    return _client


def get_session(phone: str) -> Any:
    """Get or create the Gemini chat session dedicated to one phone number."""
    with _session_guard:
        if phone not in sessions_customer:
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            config = types.GenerateContentConfig(
                system_instruction=build_system_prompt(phone),
                tools=_session_tools(phone),
                temperature=0.2,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=15),
            )
            sessions_customer[phone] = _get_client().chats.create(model=model, config=config)
            _session_turns[phone] = 0
        return sessions_customer[phone]


def reset_session(phone: str) -> None:
    """Forget one chat session and its verbose tool trace."""
    with _session_guard:
        sessions_customer.pop(phone, None)
        _session_turns.pop(phone, None)
        _last_tool_calls.pop(phone, None)


def get_last_tool_calls(phone: str) -> list[dict[str, Any]]:
    """Return a copy of the most recent tool trace for simulator diagnostics."""
    return list(_last_tool_calls.get(phone, []))


def _is_arabic(text: str) -> bool:
    """Detect whether text contains Arabic-script characters."""
    return bool(re.search(r"[\u0600-\u06FF]", text))


def _friendly_error(text: str) -> str:
    """Generate a localized, non-factual fallback if Gemini is unavailable."""
    if _is_arabic(text):
        return "عذرًا، حصلت مشكلة مؤقتة. جرّب مرة أخرى بعد قليل."
    return "Sorry, I hit a temporary problem. Please try again in a moment."


def _is_transient(error: Exception) -> bool:
    """Identify retryable Gemini quota and server errors without SDK-specific classes."""
    message = str(error).lower()
    return any(code in message for code in ("429", "500", "502", "503", "504", "timeout"))


def handle_message(phone: str, text: str) -> str:
    """Send one customer message to its Gemini chat and return the final grounded reply."""
    if not phone or not text.strip():
        return _friendly_error(text)
    lock = _session_locks[phone]
    with lock:
        if _session_turns[phone] >= MAX_SESSION_TURNS:
            reset_session(phone)
        _last_tool_calls[phone] = []
        for attempt in range(2):
            try:
                response = get_session(phone).send_message(text)
                _session_turns[phone] += 1
                reply = getattr(response, "text", None)
                if reply:
                    return reply
                LOGGER.warning("Gemini returned no text for phone %s", phone)
                return _friendly_error(text)
            except Exception as exc:  # Gemini SDK errors vary between releases.
                if attempt == 0 and _is_transient(exc):
                    LOGGER.warning("Transient Gemini error for %s; retrying: %s", phone, exc)
                    time.sleep(0.5)
                    continue
                LOGGER.exception("Unable to handle message for %s", phone)
                return _friendly_error(text)
    return _friendly_error(text)
