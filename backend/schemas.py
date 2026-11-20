"""Pydantic schemas used by the store API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Category Schemas ---
class CategoryResponse(BaseModel):
    id: int
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


# --- Product Schemas ---
class ProductResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    price: float
    stock: int
    category_id: int

    model_config = ConfigDict(from_attributes=True)


# --- Cart Schemas ---
class CartItemAdd(BaseModel):
    customer_name: str
    product_id: int
    quantity: int = Field(default=1, gt=0)


class CartItemResponse(BaseModel):
    id: int
    customer_name: str
    product_id: int
    product_name: str
    unit_price: float
    quantity: int
    subtotal: float

    model_config = ConfigDict(from_attributes=True)


class CartSummaryResponse(BaseModel):
    customer_name: str
    items: list[CartItemResponse]
    total_items: int
    total: float


# --- Order Schemas ---
class CheckoutRequest(BaseModel):
    customer_name: str
    shipping_address: str = Field(min_length=1)


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    unit_price: float
    quantity: int
    subtotal: float

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    order_id: int
    customer_name: str
    shipping_address: str
    total: float
    status: str
    created_at: datetime
    items: list[OrderItemResponse]
