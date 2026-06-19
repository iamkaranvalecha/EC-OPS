from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.orders.models import OrderStatus


class OrderItemCreate(BaseModel):
    product_name: str
    quantity: int
    price: Decimal


class OrderCreate(BaseModel):
    customer_name: str
    items: list[OrderItemCreate]


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    product_name: str
    quantity: int
    price: Decimal


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_name: str
    status: OrderStatus
    created_at: datetime
    updated_at: datetime | None
    items: list[OrderItemResponse]
