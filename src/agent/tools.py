from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.retrieval import retrieve_similar_orders
from src.orders.exceptions import OrderNotCancellable, OrderNotFound
from src.orders.models import OrderStatus
from src.orders.schemas import OrderCreate, OrderItemCreate
from src.orders.service import (
    cancel_order,
    create_order,
    find_orders_by_product,
    get_order,
    list_orders,
)


def build_mcp_server(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID | None = None,
) -> FastMCP:
    mcp = FastMCP("ec-ops-orders")

    @mcp.tool()
    async def create_order_tool(
        customer_name: str,
        items: list[dict],
    ) -> dict:
        """Create a new order with one or more items.

        Each item must have: product_name (str), quantity (int >0), price (str decimal >=0).
        customer_name must be non-empty.
        Pydantic field validators from OrderCreate/OrderItemCreate run here — same
        constraints as the REST API. Returns the created order as a dict.
        """
        try:
            order_data = OrderCreate(
                customer_name=customer_name,
                items=[
                    OrderItemCreate(
                        product_name=i["product_name"],
                        quantity=i["quantity"],
                        price=Decimal(str(i["price"])),
                    )
                    for i in items
                ],
            )
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid order data: {exc}") from exc
        async with session_factory() as session:
            order = await create_order(order_data, session, user_id=user_id)
            result = {
                "id": str(order.id),
                "customer_name": order.customer_name,
                "status": order.status.value,
                "items": [
                    {
                        "id": str(item.id),
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "price": str(item.price),
                    }
                    for item in order.items
                ],
            }
        return result

    @mcp.tool()
    async def get_order_tool(order_id: str) -> dict:
        """Retrieve a single order by its UUID.

        Raises an error if the order does not exist or does not belong to the current user.
        """
        try:
            order_uuid = UUID(order_id)
        except ValueError:
            raise ValueError(f"Invalid order ID — expected a UUID, got: {order_id!r}")
        try:
            async with session_factory() as session:
                order = await get_order(order_uuid, session, user_id=user_id)
                result = {
                    "id": str(order.id),
                    "customer_name": order.customer_name,
                    "status": order.status.value,
                    "items": [
                        {
                            "id": str(item.id),
                            "product_name": item.product_name,
                            "quantity": item.quantity,
                            "price": str(item.price),
                        }
                        for item in order.items
                    ],
                }
        except OrderNotFound as exc:
            raise ValueError(str(exc)) from exc
        return result

    @mcp.tool()
    async def list_orders_tool(status: str | None = None) -> list[dict]:
        """List all orders for the current user, optionally filtered by status.

        status must be one of: PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED
        (or omitted for all). An invalid status string raises a descriptive error.
        """
        status_enum: OrderStatus | None = None
        if status:
            try:
                status_enum = OrderStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in OrderStatus)
                raise ValueError(
                    f"Invalid status '{status}'. Must be one of: {valid}"
                )
        async with session_factory() as session:
            orders = await list_orders(session, status=status_enum, user_id=user_id)
        return [
            {
                "id": str(o.id),
                "customer_name": o.customer_name,
                "status": o.status.value,
            }
            for o in orders
        ]

    @mcp.tool()
    async def cancel_order_tool(order_id: str) -> str:
        """Cancel an order by its UUID.

        Only PENDING orders that belong to the current user can be cancelled.
        The order is soft-deleted: its status is set to CANCELLED and the
        record is retained for audit purposes.
        Returns 'cancelled' on success.
        """
        try:
            order_uuid = UUID(order_id)
        except ValueError:
            raise ValueError(f"Invalid order ID — expected a UUID, got: {order_id!r}")
        try:
            async with session_factory() as session:
                await cancel_order(order_uuid, session, user_id=user_id)
        except (OrderNotFound, OrderNotCancellable) as exc:
            raise ValueError(str(exc)) from exc
        return "cancelled"

    @mcp.tool()
    async def find_orders_by_product_tool(
        product_name: str,
        status: str | None = None,
    ) -> list[dict]:
        """Find orders containing items that match a product name (case-insensitive partial match).

        Use this when the user refers to an order by product name instead of an order ID
        (e.g. 'my refrigerator order', 'the widget order').
        product_name: partial product name to search for.
        status: optional filter — PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED.
        Returns a list of matching orders with id, customer_name, status, and items.
        """
        status_enum: OrderStatus | None = None
        if status:
            try:
                status_enum = OrderStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in OrderStatus)
                raise ValueError(f"Invalid status '{status}'. Must be one of: {valid}")
        async with session_factory() as session:
            orders = await find_orders_by_product(
                product_name, session, status=status_enum, user_id=user_id
            )
        return [
            {
                "id": str(o.id),
                "customer_name": o.customer_name,
                "status": o.status.value,
                "items": [
                    {
                        "id": str(item.id),
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "price": str(item.price),
                    }
                    for item in o.items
                ],
            }
            for o in orders
        ]

    @mcp.tool()
    async def search_orders(query: str, top_k: int = 5) -> list:
        """Search orders by semantic similarity.

        Stub — returns empty list until embeddings are wired.
        query: natural-language description of the orders to find.
        top_k: maximum number of results to return.
        """
        # Stub: no DB needed until embeddings are wired; session arg is ignored by the stub
        return await retrieve_similar_orders(query, None, top_k=top_k)  # type: ignore[arg-type]

    return mcp
