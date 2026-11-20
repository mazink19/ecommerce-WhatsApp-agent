"""FastAPI routes for the e-commerce store."""

# FastAPI dependencies use Depends(...) as parameter defaults by design.
# ruff: noqa: B008

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import models, schemas
from .database import engine, get_db

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="E-Commerce Store API", version="1.0.0")


def cart_item_data(item: models.CartItem) -> dict[str, object]:
    """Serialize one cart item with its live product price."""
    return {
        "id": item.id,
        "customer_name": item.customer_name,
        "product_id": item.product_id,
        "product_name": item.product.name,
        "unit_price": item.product.price,
        "quantity": item.quantity,
        "subtotal": round(item.product.price * item.quantity, 2),
    }


def order_data(order: models.Order) -> dict[str, object]:
    """Serialize an order using its immutable price snapshots."""
    return {
        "order_id": order.id,
        "customer_name": order.customer_name,
        "shipping_address": order.shipping_address,
        "total": order.total,
        "status": order.status,
        "created_at": order.created_at,
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "unit_price": item.unit_price,
                "quantity": item.quantity,
                "subtotal": round(item.unit_price * item.quantity, 2),
            }
            for item in order.items
        ],
    }


@app.get("/categories/", response_model=list[schemas.CategoryResponse])
def list_categories(db: Session = Depends(get_db)) -> list[models.Category]:
    """List all store categories."""
    return db.query(models.Category).order_by(models.Category.id).all()


@app.get("/products/", response_model=list[schemas.ProductResponse])
def list_products(
    keyword: str = "",
    category_id: int | None = None,
    in_stock_only: bool = False,
    db: Session = Depends(get_db),
) -> list[models.Product]:
    """Search products by a partial name or description and optional category."""
    query = db.query(models.Product)
    if keyword.strip():
        match = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                models.Product.name.ilike(match),
                models.Product.description.ilike(match),
            )
        )
    if category_id is not None:
        query = query.filter(models.Product.category_id == category_id)
    if in_stock_only:
        query = query.filter(models.Product.stock > 0)
    return query.order_by(models.Product.id).all()


@app.get("/products/{product_id}/", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)) -> models.Product:
    """Return details and live inventory for a product."""
    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.get("/cart/{customer_name}/", response_model=schemas.CartSummaryResponse)
def get_cart(customer_name: str, db: Session = Depends(get_db)) -> dict[str, object]:
    """Return a customer's cart, including calculated line totals."""
    items = (
        db.query(models.CartItem)
        .filter(models.CartItem.customer_name == customer_name)
        .order_by(models.CartItem.id)
        .all()
    )
    item_data = [cart_item_data(item) for item in items]
    return {
        "customer_name": customer_name,
        "items": item_data,
        "total_items": sum(item.quantity for item in items),
        "total": round(sum(float(item["subtotal"]) for item in item_data), 2),
    }


@app.post("/cart/items/", response_model=schemas.CartItemResponse, status_code=201)
def add_cart_item(
    payload: schemas.CartItemAdd, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Add stock-validated quantity to a customer's cart, merging existing lines."""
    product = db.get(models.Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    existing = (
        db.query(models.CartItem)
        .filter(
            models.CartItem.customer_name == payload.customer_name,
            models.CartItem.product_id == payload.product_id,
        )
        .first()
    )
    requested = payload.quantity + (existing.quantity if existing else 0)
    if requested > product.stock:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product.stock} unit(s) of {product.name} are available",
        )
    if existing:
        existing.quantity = requested
        cart_item = existing
    else:
        cart_item = models.CartItem(
            customer_name=payload.customer_name,
            product_id=payload.product_id,
            quantity=payload.quantity,
        )
        db.add(cart_item)
    db.commit()
    db.refresh(cart_item)
    return cart_item_data(cart_item)


@app.delete("/cart/items/{item_id}/")
def remove_cart_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    """Remove one cart line by its ID."""
    item = db.get(models.CartItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    db.delete(item)
    db.commit()
    return {"detail": "Cart item removed"}


@app.delete("/cart/{customer_name}/")
def clear_cart(customer_name: str, db: Session = Depends(get_db)) -> dict[str, str]:
    """Remove all lines from a customer's cart."""
    db.query(models.CartItem).filter(
        models.CartItem.customer_name == customer_name
    ).delete()
    db.commit()
    return {"detail": "Cart cleared"}


@app.post("/orders/checkout/", response_model=schemas.OrderResponse, status_code=201)
def checkout(
    payload: schemas.CheckoutRequest, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Atomically create an order, decrement inventory, and empty its cart."""
    try:
        cart_items = (
            db.query(models.CartItem)
            .filter(models.CartItem.customer_name == payload.customer_name)
            .order_by(models.CartItem.id)
            .all()
        )
        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")
        for item in cart_items:
            if item.quantity > item.product.stock:
                raise HTTPException(
                    status_code=400,
                    detail=f"Only {item.product.stock} unit(s) of {item.product.name} are available",
                )
        total = round(sum(item.product.price * item.quantity for item in cart_items), 2)
        order = models.Order(
            customer_name=payload.customer_name,
            shipping_address=payload.shipping_address,
            total=total,
            status="pending",
        )
        db.add(order)
        db.flush()
        for item in cart_items:
            db.add(
                models.OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.product.price,
                )
            )
            item.product.stock -= item.quantity
            db.delete(item)
        db.commit()
        db.refresh(order)
        return order_data(order)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@app.get("/orders/{order_id}/", response_model=schemas.OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Return one saved order with price snapshots and delivery address."""
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_data(order)


@app.put("/orders/{order_id}/cancel/", response_model=schemas.OrderResponse)
def cancel_order(order_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """Cancel a pending or confirmed order and restore its inventory."""
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in {"pending", "confirmed"}:
        raise HTTPException(
            status_code=400, detail=f"Order cannot be cancelled while {order.status}"
        )
    try:
        for item in order.items:
            product = db.get(models.Product, item.product_id)
            if product is not None:
                product.stock += item.quantity
        order.status = "cancelled"
        db.commit()
        db.refresh(order)
        return order_data(order)
    except Exception:
        db.rollback()
        raise
