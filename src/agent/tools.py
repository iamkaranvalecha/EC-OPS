from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.retrieval import retrieve_similar_orders
from src.orders.exceptions import OrderNotCancellable, OrderNotFound
from src.orders.models import OrderStatus
from src.orders.schemas import OrderCreate, OrderItemCreate
from src.orders.service import (
    cancel_order,
    create_order,
    get_order,
    list_orders,
)


def build_mcp_server(session_factory: async_sessionmaker[AsyncSession]) -> FastMCP:
    mcp = FastMCP("ec-ops-orders")

    @mcp.tool()
    async def create_order_tool(
        customer_name: str,
        items: list[dict],
    ) -> dict:
        """Create a new order with one or more items.

        Each item must have: product_name (str), quantity (int), price (str decimal).
        Returns the created order as a dict.
        """
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
        async with session_factory() as session:
            order = await create_order(order_data, session)
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

        Raises an error if the order does not exist.
        """
        try:
            async with session_factory() as session:
                order = await get_order(UUID(order_id), session)
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
        """List all orders, optionally filtered by status.

        status must be one of: PENDING, PROCESSING, SHIPPED, DELIVERED (or omitted for all).
        """
        status_enum = OrderStatus(status) if status else None
        async with session_factory() as session:
            orders = await list_orders(session, status=status_enum)
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

        Only PENDING orders can be cancelled. Raises an error otherwise.
        Returns 'cancelled' on success.
        """
        try:
            async with session_factory() as session:
                await cancel_order(UUID(order_id), session)
        except (OrderNotFound, OrderNotCancellable) as exc:
            raise ValueError(str(exc)) from exc
        return "cancelled"

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
