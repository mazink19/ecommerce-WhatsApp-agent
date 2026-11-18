"""Contract tests for the FastAPI store backend."""

import pytest
from fastapi.testclient import TestClient

from backend import models
from backend.database import Base, SessionLocal, engine
from backend.main import app


@pytest.fixture(autouse=True)
def store_data() -> None:
    """Reset the database and insert a compact deterministic catalog."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        computers = models.Category(name="Computers", description="Computer gear")
        audio = models.Category(name="Audio", description="Audio gear")
        db.add_all([computers, audio])
        db.flush()
        db.add_all(
            [
                models.Product(
                    name="Mechanical Keyboard",
                    description="Tactile RGB keyboard",
                    price=89.99,
                    stock=3,
                    category_id=computers.id,
                ),
                models.Product(
                    name="Gaming Mouse",
                    description="High DPI mouse",
                    price=49.99,
                    stock=5,
                    category_id=computers.id,
                ),
                models.Product(
                    name="Sold Out Speaker",
                    description="Portable audio speaker",
                    price=59.99,
                    stock=0,
                    category_id=audio.id,
                ),
            ]
        )
        db.commit()


@pytest.fixture
def client() -> TestClient:
    """Create an in-process HTTP client."""
    return TestClient(app)


def test_product_search_includes_description_and_stock_filter(client: TestClient) -> None:
    """Keyword searches are case-insensitive partial matches on names and descriptions."""
    response = client.get("/products/", params={"keyword": "KEYBOARD", "in_stock_only": True})
    assert response.status_code == 200
    assert [product["name"] for product in response.json()] == ["Mechanical Keyboard"]

    response = client.get("/products/", params={"keyword": "audio", "in_stock_only": True})
    assert response.status_code == 200
    assert response.json() == []


def test_cart_merges_lines_and_rejects_excess_stock(client: TestClient) -> None:
    """A cart keeps one product line and cannot reserve beyond inventory."""
    first = client.post("/cart/items/", json={"customer_name": "2010", "product_id": 1, "quantity": 1})
    assert first.status_code == 201
    merged = client.post("/cart/items/", json={"customer_name": "2010", "product_id": 1, "quantity": 2})
    assert merged.status_code == 201
    assert merged.json()["quantity"] == 3

    rejected = client.post("/cart/items/", json={"customer_name": "2010", "product_id": 1, "quantity": 1})
    assert rejected.status_code == 400
    assert "Only 3" in rejected.json()["detail"]


def test_checkout_decrements_stock_and_cancel_restores_it(client: TestClient) -> None:
    """Checkout and cancellation preserve inventory integrity."""
    added = client.post("/cart/items/", json={"customer_name": "2010", "product_id": 1, "quantity": 2})
    assert added.status_code == 201

    checkout = client.post(
        "/orders/checkout/",
        json={"customer_name": "2010", "shipping_address": "Cairo - Maadi"},
    )
    assert checkout.status_code == 201
    order = checkout.json()
    assert order["total"] == 179.98
    assert client.get("/products/1/").json()["stock"] == 1
    assert client.get("/cart/2010/").json()["items"] == []

    cancelled = client.put(f"/orders/{order['order_id']}/cancel/")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.get("/products/1/").json()["stock"] == 3

    repeated = client.put(f"/orders/{order['order_id']}/cancel/")
    assert repeated.status_code == 400


def test_empty_cart_checkout_is_rejected(client: TestClient) -> None:
    """Checkout must not create an order for an empty cart."""
    response = client.post(
        "/orders/checkout/",
        json={"customer_name": "nobody", "shipping_address": "Cairo"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Cart is empty"}


def test_route_contract_exposes_exactly_ten_store_routes(client: TestClient) -> None:
    """The OpenAPI contract contains the ten specified store operations."""
    paths = client.get("/openapi.json").json()["paths"]
    operations = {(method.upper(), path) for path, item in paths.items() for method in item if method != "parameters"}
    assert operations == {
        ("GET", "/categories/"),
        ("GET", "/products/"),
        ("GET", "/products/{product_id}/"),
        ("GET", "/cart/{customer_name}/"),
        ("POST", "/cart/items/"),
        ("DELETE", "/cart/items/{item_id}/"),
        ("DELETE", "/cart/{customer_name}/"),
        ("POST", "/orders/checkout/"),
        ("GET", "/orders/{order_id}/"),
        ("PUT", "/orders/{order_id}/cancel/"),
    }
