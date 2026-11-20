"""Gemini-powered, session-isolated sales assistant."""

from __future__ import annotations

import json
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
from groq import APIError as GroqAPIError
from groq import Groq
from requests import RequestException

from tools import ALL_TOOLS

load_dotenv()
LOGGER = logging.getLogger(__name__)
MAX_SESSION_TURNS = 40
GROQ_REQUEST_TIMEOUT_SECONDS = 20.0
GROQ_MAX_RETRIES = 1
DEFAULT_MAX_TOOL_CALLS_PER_TURN = 8
sessions_customer: dict[str, Any] = {}
_session_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_session_guard = threading.Lock()
_session_turns: dict[str, int] = defaultdict(int)
_last_tool_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
_single_requested_quantity: dict[str, int | None] = defaultdict(lambda: None)
_clarification_state: dict[str, str | None] = defaultdict(lambda: None)
_pending_quantity: dict[str, dict[str, Any]] = {}
_turn_additions: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
_client: Any | None = None
_provider = "gemini"
_groq_tools: dict[str, Callable[..., dict[str, Any]]] = {}


class GroqChatSession:
    """Small chat-compatible wrapper implementing Groq's explicit tool loop."""

    def __init__(
        self,
        phone: str,
        client: Any,
        model: str,
        tools: list[Callable[..., dict[str, Any]]],
    ) -> None:
        self.phone = phone
        self.client = client
        self.model = model
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(phone)}
        ]
        self.tool_schemas = [_groq_tool_schema(tool) for tool in tools]
        self.tools = {tool.__name__: tool for tool in tools}

    def send_message(self, text: str) -> Any:
        """Complete one user turn, executing Groq tool calls until text is returned."""
        language = detect_language(text)
        self.messages.append(
            {
                "role": "system",
                "content": f"For the next reply, use {language}. This latest message overrides prior language.",
            }
        )
        self.messages.append({"role": "user", "content": text})
        max_calls = max(
            1,
            int(os.getenv("MAX_TOOL_CALLS_PER_TURN", DEFAULT_MAX_TOOL_CALLS_PER_TURN)),
        )
        executed_calls = 0
        seen_calls: dict[tuple[str, str], dict[str, Any]] = {}
        for _ in range(max_calls + 1):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.tool_schemas,
                tool_choice="auto",
                temperature=0.2,
            )
            message = response.choices[0].message
            self.messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                return type("Response", (), {"text": message.content or ""})()
            for call in message.tool_calls:
                function = self.tools.get(call.function.name)
                raw_arguments = call.function.arguments or "{}"
                key = (call.function.name, raw_arguments)
                if key in seen_calls:
                    result = seen_calls[key]
                elif executed_calls >= max_calls:
                    result = {
                        "success": False,
                        "error": "Turn tool-call limit reached; no further action was executed.",
                    }
                if function is None:
                    result: dict[str, Any] = {"success": False, "error": "Unknown tool"}
                elif key not in seen_calls and executed_calls < max_calls:
                    try:
                        arguments = json.loads(raw_arguments)
                        result = function(**arguments)
                    except (
                        ValueError,
                        TypeError,
                        KeyError,
                        RuntimeError,
                        RequestException,
                    ) as exc:
                        result = {
                            "success": False,
                            "error": f"Tool call failed ({type(exc).__name__}).",
                        }
                    seen_calls[key] = result
                    executed_calls += 1
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        raise RuntimeError(
            "Groq did not produce a final response within the configured tool-call limit"
        )


def _groq_tool_schema(tool: Callable[..., Any]) -> dict[str, Any]:
    """Convert one annotated Python tool into a Groq JSON function schema."""
    import inspect

    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in inspect.signature(tool).parameters.items():
        annotation = parameter.annotation
        json_type = (
            "integer"
            if annotation is int
            else "boolean"
            if annotation is bool
            else "string"
        )
        properties[name] = {"type": json_type}
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "type": "function",
        "function": {
            "name": tool.__name__,
            "description": tool.__doc__ or tool.__name__,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def build_system_prompt(phone: str) -> str:
    """Build the non-negotiable store policy for one customer session."""
    store_name = os.getenv("STORE_NAME", "My Store")
    return f"""You are the concise sales assistant for {store_name}.
        The customer's ID is `{phone}`. Always pass this exact value as `customer_name` for cart and checkout tools.

        STRICT CURRENT-TURN VERIFICATION (HALLUCINATION ZERO): Never state, repeat, estimate, infer, or rely on a price or stock quantity from conversation history. For EVERY user turn asking about a product price or stock/availability, call the relevant backend tool(s) during THIS turn and use only the returned current result. A result from an earlier turn is stale and is not evidence. If the backend tool was not called in this turn, the result is missing, or the tool fails, do not provide any price or stock number; explain that you could not verify it. Never invent or guess cart contents, order status, product availability, order number, or total; verify these with the relevant backend tool in the current turn before stating them.
        Handle compound requests completely in one turn. Search every requested item first, then add each selected item. Only check out when the customer explicitly asks to check out and has supplied a shipping address. Without an address, ask for it. If the customer has not explicitly requested checkout, confirm the cart instead.
        The catalog product names are English. When an Arabic customer uses a transliterated name, search its likely English catalog term (for example, "كيبورد ميكانيكال" means "Mechanical Keyboard" and "ماوس جيمينج" means "Gaming Mouse") rather than searching the Arabic transliteration literally. Product search results may include `in_stock_alternatives`; list these grounded alternatives when an item is unavailable.
        Never silently reduce or change a quantity the customer requested. If the requested quantity exceeds available stock, do not add any units; state the exact available quantity from the tool result and offer that quantity instead.
        If a searched item has stock 0, say so, then you MUST call search_products again with that result's category_id and in_stock_only=True before replying. Offer the returned alternatives if any. If the cart is empty, explain that and offer help rather than calling checkout.
        SCOPE: You are a store sales assistant only. Answer questions about this store, its products, prices, stock, cart, checkout, shipping, and orders. For unrelated topics (for example sports, politics, general trivia, or entertainment), politely say you can only help with store matters and redirect the customer to products, prices, stock, cart, or orders. Do not answer the unrelated question and do not call store tools for it.
        For all prices, stock levels, and product availability:
        never invent or guess. You MUST call the relevant backend
        tool during the current user turn before providing any
        price or stock information. Never rely on previous turns.

        CURRENCY FORMATTING:
        The store currency is Egyptian Pound (EGP).
        Always format prices as 49.99 EGP.
        For Arabic responses, format prices as 49.99 ج.م.
        Never use currency symbols such as ₱, $, or £.
        Never put a foreign currency symbol before a price.
        Always reply in the customer's language based on the latest
        user message, not the previous conversation language.
        LATEST customer message:
        Always prioritize the LATEST customer message when interpreting
        the current request. Reply based on the latest message, not
        previous conversation language or intent.
        Use WhatsApp *bold* for prices, product names, order numbers, and totals."""


def bind_customer_tool(
    tool: Callable[..., dict[str, Any]], phone: str
) -> Callable[..., dict[str, Any]]:
    """Return a schema-preserving tool wrapper that logs calls and pins cart identity."""
    import inspect

    signature = inspect.signature(tool)

    @wraps(tool)
    def bound_tool(*args: Any, **kwargs: Any) -> dict[str, Any]:
        bound = signature.bind_partial(*args, **kwargs)
        if "customer_name" in signature.parameters:
            bound.arguments["customer_name"] = phone
        if tool.__name__ == "add_item_to_cart":
            product_id = int(bound.arguments["product_id"])
            quantity = int(bound.arguments.get("quantity", 1))
            if product_id in _turn_additions[phone]:
                return _turn_additions[phone][product_id]
            stock_result = ALL_TOOLS[2](product_id)
            _last_tool_calls[phone].append(
                {
                    "tool": "get_product_details",
                    "arguments": {"product_id": product_id},
                    "result": stock_result,
                }
            )
            if not stock_result.get("success"):
                return {
                    "success": False,
                    "error": "Could not verify current stock; no item was added.",
                }
            product = stock_result.get("data", stock_result)
            available = int(product.get("stock", 0))
            if quantity > available:
                _pending_quantity[phone] = {
                    "product_id": product_id,
                    "product_name": product.get("name", "the requested product"),
                    "requested": quantity,
                    "available": available,
                }
                return {
                    "success": False,
                    "error": f"Requested {quantity}, current available stock is {available}. Do not add any quantity. Ask whether the customer explicitly approves adding exactly {available}.",
                }
        requested_quantity = _single_requested_quantity.get(phone)
        if tool.__name__ == "add_item_to_cart" and requested_quantity is not None:
            proposed_quantity = int(bound.arguments.get("quantity", 1))
            if proposed_quantity != requested_quantity:
                result = {
                    "success": False,
                    "error": (
                        f"Customer explicitly requested {requested_quantity} unit(s). Do not silently change "
                        f"the quantity to {proposed_quantity}; retry with the requested quantity so stock can be checked."
                    ),
                }
                _last_tool_calls[phone].append(
                    {
                        "tool": tool.__name__,
                        "arguments": dict(bound.arguments),
                        "result": result,
                    }
                )
                return result
        result = tool(*bound.args, **bound.kwargs)
        if tool.__name__ == "add_item_to_cart" and result.get("success"):
            _turn_additions[phone][int(bound.arguments["product_id"])] = result
        _last_tool_calls[phone].append(
            {
                "tool": tool.__name__,
                "arguments": dict(bound.arguments),
                "result": result,
            }
        )
        return result

    return bound_tool


def _session_tools(phone: str) -> list[Callable[..., dict[str, Any]]]:
    """Bind all identity-sensitive functions to a session's phone."""
    return [bind_customer_tool(tool, phone) for tool in ALL_TOOLS]


def _get_client() -> Any:
    """Create the Gemini client lazily so local tests do not require a secret."""
    global _client
    global _provider
    _provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    if _client is None:
        if _provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise RuntimeError("GROQ_API_KEY is not configured")
            _client = Groq(
                api_key=api_key,
                timeout=GROQ_REQUEST_TIMEOUT_SECONDS,
                max_retries=GROQ_MAX_RETRIES,
            )
            return _client
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
            tools = _session_tools(phone)
            if os.getenv("AI_PROVIDER", "gemini").strip().lower() == "groq":
                client = _get_client()
                model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
                sessions_customer[phone] = GroqChatSession(phone, client, model, tools)
                _session_turns[phone] = 0
                return sessions_customer[phone]
            _provider = "gemini"
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            config = types.GenerateContentConfig(
                system_instruction=build_system_prompt(phone),
                tools=tools,
                temperature=0.2,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=15
                ),
            )
            sessions_customer[phone] = _get_client().chats.create(
                model=model, config=config
            )
            _session_turns[phone] = 0
        return sessions_customer[phone]


def reset_session(phone: str) -> None:
    """Forget one chat session and its verbose tool trace."""
    with _session_guard:
        sessions_customer.pop(phone, None)
        _session_turns.pop(phone, None)
        _last_tool_calls.pop(phone, None)
        _pending_quantity.pop(phone, None)
        _turn_additions.pop(phone, None)


def get_last_tool_calls(phone: str) -> list[dict[str, Any]]:
    """Return a copy of the most recent tool trace for simulator diagnostics."""
    return list(_last_tool_calls.get(phone, []))


def _is_arabic(text: str) -> bool:
    """Detect whether text contains Arabic-script characters."""
    return bool(re.search(r"[\u0600-\u06FF]", text))


def detect_language(text: str) -> str:
    """Identify the dominant language from the latest user message."""
    arabic = len(re.findall(r"[\u0600-\u06FF]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "Arabic" if arabic > latin else "English"


def _is_ambiguous_mouse_request(text: str) -> bool:
    """Detect generic mouse requests without a specific model or type."""
    normalized = re.sub(r"[^a-zA-Z\s]", " ", text).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()

    generic_words = {
        "i",
        "want",
        "would",
        "like",
        "could",
        "can",
        "you",
        "please",
        "to",
        "buy",
        "a",
        "an",
        "the",
        "show",
        "me",
        "find",
        "search",
        "for",
        "add",
        "get",
        "order",
        "one",
        "some",
        "my",
        "cart",
    }

    remaining_words = [word for word in normalized.split() if word not in generic_words]

    return remaining_words == ["mouse"]


def _quantity_confirmation(text: str) -> bool | None:
    """Parse an explicit yes/no response to a pending partial-stock offer."""
    normalized = text.strip().lower()
    if normalized in {
        "yes",
        "yes please",
        "add them",
        "add it",
        "okay",
        "ok",
        "sure",
        "نعم",
        "أيوه",
        "ايوه",
        "تمام",
        "موافق",
    }:
        return True
    if normalized in {"no", "no thanks", "don't", "do not", "لا", "مش عايز", "لا شكرا"}:
        return False
    return None


def _quantity_request(text: str) -> tuple[int, str] | None:
    """Extract one explicit add quantity and its product phrase."""
    normalized = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    numbers = re.findall(r"\b\d+\b", normalized)
    if len(numbers) != 1 or not re.search(
        r"\b(add|buy|put|place)\b|أضف|ضيف", normalized, re.IGNORECASE
    ):
        return None
    quantity = int(numbers[0])
    phrase = re.sub(r"\b\d+\b", " ", normalized)
    phrase = re.sub(
        r"(?i)\b(add|buy|put|place|to|my|the|cart|please|units?|pieces?)\b", " ", phrase
    )
    phrase = re.sub(r"أضف|ضيف|إلى|للسلة|السلة|قطعة|قطع", " ", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip(" .,!؟")
    return (quantity, phrase) if quantity > 0 and phrase else None


def _preflight_excess_quantity(phone: str, text: str) -> str | None:
    """Check explicit quantity requests before asking the model to add anything."""
    parsed = _quantity_request(text)
    if not parsed:
        return None
    quantity, keyword = parsed
    search = ALL_TOOLS[1](keyword=keyword)
    _last_tool_calls[phone].append(
        {"tool": "search_products", "arguments": {"keyword": keyword}, "result": search}
    )
    if not search.get("success"):
        return "I could not check the catalog, so I have not added anything. Please try again."
    matches = search.get("data", [])
    if len(matches) != 1:
        return None
    product = matches[0]
    details = ALL_TOOLS[2](int(product["id"]))
    _last_tool_calls[phone].append(
        {
            "tool": "get_product_details",
            "arguments": {"product_id": int(product["id"])},
            "result": details,
        }
    )
    if not details.get("success"):
        return "I could not verify current stock, so I have not added anything. Please try again."
    current = details.get("data", details)
    available = int(current.get("stock", 0))
    if quantity <= available:
        return None
    _pending_quantity[phone] = {
        "product_id": int(product["id"]),
        "product_name": current.get("name", product.get("name", keyword)),
        "requested": quantity,
        "available": available,
    }
    return f"Only {available} of {_pending_quantity[phone]['product_name']} are currently available, but you requested {quantity}. I have not added anything. Would you like me to add exactly {available}?"


def _approve_pending_quantity(phone: str) -> str:
    """Recheck stock and add the approved available quantity once."""
    pending = _pending_quantity.get(phone)
    if not pending:
        return "I no longer have a pending quantity confirmation. Please send your request again."
    checked = ALL_TOOLS[2](pending["product_id"])
    _last_tool_calls[phone].append(
        {
            "tool": "get_product_details",
            "arguments": {"product_id": pending["product_id"]},
            "result": checked,
        }
    )
    if not checked.get("success"):
        return "I could not verify current stock, so nothing was added. Please try again later."
    product = checked.get("data", checked)
    current_stock = int(product.get("stock", 0))
    approved_quantity = min(int(pending["available"]), int(pending["requested"]))
    if current_stock < approved_quantity:
        pending["available"] = current_stock
        return f"Stock changed. Only {current_stock} of {pending['product_name']} are available now. Would you like me to add exactly {current_stock}?"
    result = ALL_TOOLS[4](phone, int(pending["product_id"]), approved_quantity)
    _last_tool_calls[phone].append(
        {
            "tool": "add_item_to_cart",
            "arguments": {
                "customer_name": phone,
                "product_id": pending["product_id"],
                "quantity": approved_quantity,
            },
            "result": result,
        }
    )
    if not result.get("success"):
        return f"I couldn't add the approved quantity: {result.get('error', 'store request failed')}. Nothing was confirmed as added."
    _pending_quantity.pop(phone, None)
    return f"Added {approved_quantity} of {product.get('name', pending['product_name'])} to your cart, as approved."


def _friendly_error(text: str) -> str:
    """Generate a localized, non-factual fallback if Gemini is unavailable."""
    if _is_arabic(text):
        return "عذرًا، حصلت مشكلة مؤقتة. جرّب مرة أخرى بعد قليل."
    return "Sorry, I hit a temporary problem. Please try again in a moment."


def _is_transient(error: Exception) -> bool:
    """Identify retryable Gemini quota and server errors without SDK-specific classes."""
    message = str(error).lower()
    return any(
        code in message for code in ("429", "500", "502", "503", "504", "timeout")
    )


def _explicit_single_quantity(text: str) -> int | None:
    """Extract one explicit numeric add quantity while avoiding multi-product requests."""
    normalized = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    matches = re.findall(r"\b\d+\b", normalized)
    lowered = normalized.lower()
    if len(matches) != 1 or " and " in lowered or " و" in normalized:
        return None
    value = int(matches[0])
    return value if value > 0 else None


def _requires_live_catalog_check(text: str) -> bool:
    """Return whether this turn asks for a current product price or stock fact."""
    normalized = text.lower()
    terms = (
        "price",
        "how much",
        "cost",
        "السعر",
        "بكام",
        "كم سعر",
        "ثمن",
        "تكلفة",
        "سعره",
        "سعرها",
        "stock",
        "available",
        "availability",
        "in stock",
        "out of stock",
        "متوفر",
        "المخزون",
        "عندكم",
        "فيه منه",
        "موجود",
        "متاح",
    )
    return any(term in normalized for term in terms)


def _has_current_catalog_check(phone: str) -> bool:
    """Check whether a successful catalog lookup ran during the current turn."""
    return any(
        call.get("tool") in {"search_products", "get_product_details"}
        and isinstance(call.get("result"), dict)
        and call["result"].get("success") is True
        for call in _last_tool_calls.get(phone, [])
    )


def _localized_verification_fallback(text: str) -> str:
    """Avoid exposing unverified catalog facts when the model skips its tool call."""
    if detect_language(text) == "Arabic":
        return "لا أستطيع تأكيد السعر أو المخزون حاليًا من قاعدة بيانات المتجر. حاول مرة أخرى بعد قليل."
    return "I can't verify the current price or stock from the store database right now. Please try again shortly."


def _normalize_currency_format(reply: str) -> str:
    """Remove incorrect Philippine peso symbols from store prices."""
    return re.sub(r"₱\s*(?=\d)", "", reply)


def handle_message(phone: str, text: str) -> str:
    """Send one customer message to its Gemini chat and return the final grounded reply."""
    if not phone or not text.strip():
        return _friendly_error(text)
    lock = _session_locks[phone]
    with lock:
        if _is_ambiguous_mouse_request(text):
            _clarification_state[phone] = "mouse_model"
            return "Which mouse would you like? Could you specify the model or type?"
        pending_quantity = _pending_quantity.get(phone)
        if pending_quantity:
            confirmation = _quantity_confirmation(text)
            if confirmation is True:
                return _approve_pending_quantity(phone)
            if confirmation is False:
                _pending_quantity.pop(phone, None)
                return "Understood. I did not add anything."
            return f"Please answer yes or no: should I add exactly {pending_quantity['available']} of {pending_quantity['product_name']}? I have not added anything yet."
        if _clarification_state.get(phone) == "mouse_model":
            _clarification_state.pop(phone, None)
            text = f"Find and add the customer's clarified mouse choice: {text}"
        if _session_turns[phone] >= MAX_SESSION_TURNS:
            reset_session(phone)
        _last_tool_calls[phone] = []
        _turn_additions[phone] = {}
        preflight_reply = _preflight_excess_quantity(phone, text)
        if preflight_reply:
            return preflight_reply
        _single_requested_quantity[phone] = _explicit_single_quantity(text)
        for attempt in range(2):
            try:
                session = get_session(phone)
                if os.getenv("AI_PROVIDER", "gemini").strip().lower() != "groq":
                    language = detect_language(text)
                    turn_message = (
                        f"[MANDATORY CURRENT-TURN INSTRUCTION: Reply in {language}. This latest "
                        "message overrides the language of all previous turns. For price or stock "
                        "questions, call the relevant backend tool in this turn; never reuse old data.]\n"
                        f"{text}"
                    )
                else:
                    turn_message = text
                response = session.send_message(turn_message)
                _session_turns[phone] += 1
                reply = getattr(response, "text", None)
                if reply:
                    pending = _pending_quantity.get(phone)
                    if pending:
                        return f"Only {pending['available']} of {pending['product_name']} are currently available, but you requested {pending['requested']}. I have not added anything. Would you like me to add exactly {pending['available']}?"
                    if _requires_live_catalog_check(
                        text
                    ) and not _has_current_catalog_check(phone):
                        return _localized_verification_fallback(text)
                    return _normalize_currency_format(reply)

                LOGGER.warning("Gemini returned no text for phone %s", phone)
                return _friendly_error(text)
            except (
                genai.errors.APIError,
                GroqAPIError,
                RuntimeError,
                ValueError,
            ) as exc:
                if attempt == 0 and _is_transient(exc):
                    LOGGER.warning(
                        "Transient Gemini error for %s; retrying: %s", phone, exc
                    )
                    time.sleep(0.5)
                    continue
                LOGGER.error(
                    "Unable to handle message for %s (%s)", phone, type(exc).__name__
                )
                return _friendly_error(text)
        _single_requested_quantity.pop(phone, None)
    return _friendly_error(text)
