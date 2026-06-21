import os
import uuid
from decimal import Decimal

import pytest

from src.orders.models import Order, OrderEmbedding, OrderItem, OrderStatus


def test_order_status_members():
    assert OrderStatus.PENDING == "PENDING"
    assert OrderStatus.PROCESSING == "PROCESSING"
    assert OrderStatus.SHIPPED == "SHIPPED"
    assert OrderStatus.DELIVERED == "DELIVERED"
    assert OrderStatus.CANCELLED == "CANCELLED"
    assert set(s.value for s in OrderStatus) == {
        "PENDING", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED"
    }


def test_order_table_name():
    assert Order.__tablename__ == "orders"


def test_order_columns_exist():
    columns = {c.name for c in Order.__table__.columns}
    assert "id" in columns
    assert "customer_name" in columns
    assert "status" in columns
    assert "created_at" in columns
    assert "updated_at" in columns


def test_order_item_table_name():
    assert OrderItem.__tablename__ == "order_items"


def test_order_item_columns_exist():
    columns = {c.name for c in OrderItem.__table__.columns}
    assert "id" in columns
    assert "order_id" in columns
    assert "product_name" in columns
    assert "quantity" in columns
    assert "price" in columns


def test_order_item_fk_references_orders():
    fk = next(iter(OrderItem.__table__.c.order_id.foreign_keys))
    assert fk.column.table.name == "orders"


def test_order_embedding_table_name():
    assert OrderEmbedding.__tablename__ == "order_embeddings"


def test_order_embedding_columns_exist():
    columns = {c.name for c in OrderEmbedding.__table__.columns}
    assert "id" in columns
    assert "order_id" in columns
    assert "embedding" in columns
    assert "content" in columns
    assert "created_at" in columns


def test_order_embedding_fk_references_orders():
    fk = next(iter(OrderEmbedding.__table__.c.order_id.foreign_keys))
    assert fk.column.table.name == "orders"


def test_order_default_status():
    order = Order(customer_name="Alice")
    assert order.status == OrderStatus.PENDING


def test_order_item_price_is_decimal():
    item = OrderItem(
        order_id=uuid.uuid4(),
        product_name="Widget",
        quantity=3,
        price=Decimal("9.99"),
    )
    assert item.price == Decimal("9.99")


def test_order_relationship_attribute_exists():
    assert hasattr(Order, "items")


def test_order_item_relationship_attribute_exists():
    assert hasattr(OrderItem, "order")


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="requires live test DB — set TEST_DATABASE_URL to run",
)
async def test_insert_order_with_items_db():
    import os

    from dotenv import dotenv_values
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    _env = dotenv_values(".env")
    # Always use the TEST database — never touch the application DB
    url = (
        os.environ.get("TEST_DATABASE_URL")
        or _env.get("TEST_DATABASE_URL")
        or "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops_test"
    )
    eng = create_async_engine(url, echo=False)
    session_factory = async_sessionmaker(eng, expire_on_commit=False)

    try:
        async with session_factory() as session:
            order = Order(customer_name="Test Customer", status=OrderStatus.PENDING)
            item1 = OrderItem(product_name="Widget A", quantity=2, price=Decimal("5.00"))
            item2 = OrderItem(product_name="Widget B", quantity=1, price=Decimal("15.50"))
            order.items = [item1, item2]
            session.add(order)
            await session.commit()
            await session.refresh(order)

        async with session_factory() as session:
            from sqlalchemy import select

            result = await session.execute(select(Order).where(Order.id == order.id))
            fetched = result.scalar_one()
            assert fetched.customer_name == "Test Customer"
            assert len(fetched.items) == 2
            product_names = {i.product_name for i in fetched.items}
            assert product_names == {"Widget A", "Widget B"}
    finally:
        # Do NOT drop_all — tables are shared with the test suite.
        # Row cleanup is handled by the autouse db_setup fixture (TRUNCATE orders CASCADE).
        await eng.dispose()
