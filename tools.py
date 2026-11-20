"""Documented HTTP tools that connect the Gemini agent to the store backend."""

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()
_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
_SESSION = requests.Session()
_TIMEOUT_SECONDS = 10


def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """Run one backend request and convert every transport or HTTP error to data."""
    try:
        response = _SESSION.request(
            method, f"{_BACKEND_URL}{path}", timeout=_TIMEOUT_SECONDS, **kwargs
        )
        response.raise_for_status()
        data = response.json()
        return {"success": True, **(data if isinstance(data, dict) else {"data": data})}
    except requests.HTTPError as exc:
        response = exc.response
        reason = "The store could not complete that request"
        if response is not None:
            try:
                payload = response.json()
                reason = (
                    str(payload.get("detail", reason))
                    if isinstance(payload, dict)
                    else reason
                )
            except ValueError:
                reason = response.text or reason
        return {"success": False, "error": reason}
    except requests.RequestException as exc:
        return {"success": False, "error": f"Store backend is unavailable: {exc}"}
    except ValueError:
        return {"success": False, "error": "Store backend returned invalid data"}


def list_categories() -> dict[str, Any]:
    """List store categories. Use when the customer asks what kinds of products the store carries.

    Args:
        None.

    Returns:
        A success result containing the current category list, or a human-readable error.
    """
    return _request("GET", "/categories/")


def search_products(
    keyword: str = "", category_id: int = 0, in_stock_only: bool = False
) -> dict[str, Any]:
    """Search current products. Call this before quoting any price or stock to a customer.

    Args:
        keyword: A name or description fragment to search for.
        category_id: Category ID to filter by; use 0 for no category filter.
        in_stock_only: Whether to return only products with stock available.

    Returns:
        A success result containing matching products, or a human-readable error.
    """
    params: dict[str, Any] = {"keyword": keyword, "in_stock_only": in_stock_only}
    if category_id:
        params["category_id"] = category_id
    result = _request("GET", "/products/", params=params)
    products = result.get("data")
    if result.get("success") and isinstance(products, list) and not in_stock_only:
        out_of_stock_categories = {
            product.get("category_id")
            for product in products
            if isinstance(product, dict)
            and product.get("stock", 0) == 0
            and product.get("category_id")
        }
        alternatives: list[dict[str, Any]] = []
        for unavailable_category_id in sorted(out_of_stock_categories):
            alternative_result = _request(
                "GET",
                "/products/",
                params={"category_id": unavailable_category_id, "in_stock_only": True},
            )
            if alternative_result.get("success") and isinstance(
                alternative_result.get("data"), list
            ):
                alternatives.extend(alternative_result["data"])
        if alternatives:
            result["in_stock_alternatives"] = alternatives
    return result


def get_product_details(product_id: int) -> dict[str, Any]:
    """Get a product's current details. Call before stating a specific product's price or stock.

    Args:
        product_id: The product ID returned by a product search.

    Returns:
        A success result with the product record, or a human-readable error.
    """
    return _request("GET", f"/products/{product_id}/")


def get_customer_cart(customer_name: str) -> dict[str, Any]:
    """Get a customer's live cart. Call before confirming cart contents or a cart total.

    Args:
        customer_name: The customer's WhatsApp ID.

    Returns:
        A success result containing cart lines and total, or a human-readable error.
    """
    return _request("GET", f"/cart/{customer_name}/")


def add_item_to_cart(
    customer_name: str, product_id: int, quantity: int = 1
) -> dict[str, Any]:
    """Add a product to a cart. Call only after identifying the product and requested quantity.

    Args:
        customer_name: The customer's WhatsApp ID.
        product_id: The product ID to add.
        quantity: Number of units to add, defaulting to one.

    Returns:
        A success result with the added cart line, or a human-readable stock or validation error.
    """
    return _request(
        "POST",
        "/cart/items/",
        json={
            "customer_name": customer_name,
            "product_id": product_id,
            "quantity": quantity,
        },
    )


def remove_cart_item(item_id: int) -> dict[str, Any]:
    """Remove one cart line. Call after retrieving the cart to identify its line ID.

    Args:
        item_id: The cart line ID returned by get_customer_cart.

    Returns:
        A success confirmation, or a human-readable error.
    """
    return _request("DELETE", f"/cart/items/{item_id}/")


def clear_customer_cart(customer_name: str) -> dict[str, Any]:
    """Clear a customer's cart. Call only when the customer explicitly asks to empty it.

    Args:
        customer_name: The customer's WhatsApp ID.

    Returns:
        A success confirmation, or a human-readable error.
    """
    return _request("DELETE", f"/cart/{customer_name}/")


def checkout_cart(customer_name: str, shipping_address: str) -> dict[str, Any]:
    """Check out a cart. Call only when the customer explicitly requests checkout and supplied an address.

    Args:
        customer_name: The customer's WhatsApp ID.
        shipping_address: The delivery address provided by the customer.

    Returns:
        A success result with order ID and total, or a human-readable checkout error.
    """
    return _request(
        "POST",
        "/orders/checkout/",
        json={"customer_name": customer_name, "shipping_address": shipping_address},
    )


def track_order(order_id: int) -> dict[str, Any]:
    """Get an order's current status. Call before describing any order status or total.

    Args:
        order_id: The order number supplied by the customer.

    Returns:
        A success result with the saved order, or a human-readable not-found error.
    """
    return _request("GET", f"/orders/{order_id}/")


def cancel_order(order_id: int) -> dict[str, Any]:
    """Cancel an eligible order. Call only when the customer clearly requests cancellation.

    Args:
        order_id: The order number to cancel.

    Returns:
        A success result with the cancelled order, or a human-readable error.
    """
    return _request("PUT", f"/orders/{order_id}/cancel/")


ALL_TOOLS = [
    list_categories,
    search_products,
    get_product_details,
    get_customer_cart,
    add_item_to_cart,
    remove_cart_item,
    clear_customer_cart,
    checkout_cart,
    track_order,
    cancel_order,
]
