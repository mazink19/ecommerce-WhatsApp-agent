"""Tests for the documented agent tool layer."""

import inspect
from typing import Any

import requests

import tools


class FakeResponse:
    """Small stand-in for a requests response."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> Any:
        """Return configured JSON data."""
        return self.payload

    def raise_for_status(self) -> None:
        """Raise a requests-style HTTP error for error responses."""
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class FakeSession:
    """Records HTTP requests and returns preconfigured responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(
        self, method: str, url: str, timeout: int, **kwargs: Any
    ) -> FakeResponse:
        """Return a response based on the requested path."""
        self.calls.append((method, url, kwargs))
        if url.endswith("/products/404/"):
            return FakeResponse({"detail": "Product not found"}, 404)
        if method == "POST" and kwargs.get("json", {}).get("quantity") == 99:
            return FakeResponse({"detail": "Only 2 unit(s) are available"}, 400)
        return FakeResponse({"value": "ok"})


def test_tools_return_consistent_success_and_failure_shapes(monkeypatch: Any) -> None:
    """Every public tool returns data instead of raising request exceptions."""
    fake = FakeSession()
    monkeypatch.setattr(tools, "_SESSION", fake)

    calls = [
        tools.list_categories(),
        tools.search_products("mouse", 0, True),
        tools.get_product_details(1),
        tools.get_customer_cart("2010"),
        tools.add_item_to_cart("2010", 1, 1),
        tools.remove_cart_item(1),
        tools.clear_customer_cart("2010"),
        tools.checkout_cart("2010", "Cairo"),
        tools.track_order(1),
        tools.cancel_order(1),
    ]
    assert all(result == {"success": True, "value": "ok"} for result in calls)
    assert fake.calls[1][2]["params"] == {"keyword": "mouse", "in_stock_only": True}

    failure = tools.get_product_details(404)
    assert failure == {"success": False, "error": "Product not found"}
    stock_failure = tools.add_item_to_cart("2010", 1, 99)
    assert stock_failure["success"] is False
    assert "Only 2" in stock_failure["error"]


def test_tool_catalog_has_ten_documented_annotated_functions() -> None:
    """Gemini schema introspection has the exact required function catalog."""
    assert len(tools.ALL_TOOLS) == 10
    assert [tool.__name__ for tool in tools.ALL_TOOLS] == [
        "list_categories",
        "search_products",
        "get_product_details",
        "get_customer_cart",
        "add_item_to_cart",
        "remove_cart_item",
        "clear_customer_cart",
        "checkout_cart",
        "track_order",
        "cancel_order",
    ]
    for tool in tools.ALL_TOOLS:
        assert tool.__doc__ and "Args:" in tool.__doc__ and "Returns:" in tool.__doc__
        assert inspect.get_annotations(tool)


def test_search_attaches_grounded_same_category_alternatives(monkeypatch: Any) -> None:
    """Out-of-stock searches include backend-sourced alternatives for the agent to offer."""
    responses = iter(
        [
            FakeResponse(
                [{"id": 3, "stock": 0, "category_id": 2, "name": "Sold Out Speaker"}]
            ),
            FakeResponse(
                [{"id": 4, "stock": 5, "category_id": 2, "name": "Available Speaker"}]
            ),
        ]
    )

    class SearchSession:
        """Return controlled search payloads in order."""

        def request(
            self, method: str, url: str, timeout: int, **kwargs: Any
        ) -> FakeResponse:
            """Serve the next configured search response."""
            return next(responses)

    monkeypatch.setattr(tools, "_SESSION", SearchSession())
    result = tools.search_products("speaker")
    assert result["success"] is True
    assert result["in_stock_alternatives"] == [
        {"id": 4, "stock": 5, "category_id": 2, "name": "Available Speaker"}
    ]


def test_backend_connection_failure_is_reported_without_success(
    monkeypatch: Any,
) -> None:
    """An unavailable backend remains a visible failure instead of a successful tool result."""

    class OfflineSession:
        """Simulate an unreachable API endpoint."""

        def request(self, *args: Any, **kwargs: Any) -> Any:
            raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(tools, "_SESSION", OfflineSession())
    result = tools.get_customer_cart("offline-customer")
    assert result["success"] is False
    assert "unavailable" in result["error"].lower()
