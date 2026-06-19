from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.orders.exceptions import OrderNotCancellable, OrderNotFound
from src.orders.models import OrderStatus
from src.orders.schemas import OrderCreate, OrderResponse
from src.orders.service import cancel_order, create_order, get_order, list_orders

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order_route(
    data: OrderCreate,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    order = await create_order(data, session)
    return OrderResponse.model_validate(order)


@router.get("", response_model=list[OrderResponse])
async def list_orders_route(
    status: OrderStatus | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[OrderResponse]:
    orders = await list_orders(session, status=status)
    return [OrderResponse.model_validate(o) for o in orders]


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order_route(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    try:
        order = await get_order(order_id, session)
    except OrderNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OrderResponse.model_validate(order)


@router.delete("/{order_id}", status_code=204)
async def cancel_order_route(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await cancel_order(order_id, session)
    except OrderNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OrderNotCancellable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)
