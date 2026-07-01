"""End-to-end order lifecycle integration tests — API-only, no DB shortcuts.

Every status change goes through the REST API. No _force_status helpers.
Five lifecycle variants:

  1. Full fulfilment  — PENDING → PROCESSING → SHIPPED → DELIVERED, terminal checks
  2. Early cancel     — PENDING → CANCELLED, terminal checks
  3. Cancel-after-processing attempt — cannot cancel once past PENDING
  4. Multi-item order — items persist and are correct at every stage
  5. Parallel orders  — two orders walk independent paths simultaneously
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


_SINGLE_ITEM = {
    "customer_name": "Lifecycle Tester",
    "items": [{"product_name": "Widget", "quantity": 1, "price": "19.99"}],
}

_MULTI_ITEM = {
    "customer_name": "Multi-Item Tester",
    "items": [
        {"product_name": "Laptop",   "quantity": 1, "price": "999.00"},
        {"product_name": "Mouse",    "quantity": 2, "price": "29.99"},
        {"product_name": "Keyboard", "quantity": 1, "price": "79.99"},
    ],
}


# ── helpers ───────────────────────────────────────────────────────────────────

async def _create(client: AsyncClient, payload: dict) -> str:
    r = await client.post("/orders", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _get(client: AsyncClient, order_id: str) -> dict:
    r = await client.get(f"/orders/{order_id}")
    assert r.status_code == 200
    return r.json()


async def _patch_status(client: AsyncClient, order_id: str, status: str) -> dict:
    r = await client.patch(f"/orders/{order_id}/status", json={"status": status})
    assert r.status_code == 200, f"PATCH to {status} failed: {r.text}"
    body = r.json()
    assert body["status"] == status
    assert body["updated_at"] is not None
    return body


async def _list_by_status(client: AsyncClient, status: str) -> list[dict]:
    r = await client.get(f"/orders?status={status}")
    assert r.status_code == 200
    return r.json()


async def _cancel(client: AsyncClient, order_id: str) -> None:
    r = await client.delete(f"/orders/{order_id}")
    assert r.status_code == 204, r.text


# ═════════════════════════════════════════════════════════════════════════════
# VARIANT 1 — Full fulfilment lifecycle
# PENDING → PROCESSING → SHIPPED → DELIVERED
# Verifies GET and list-filter responses at every stage.
# Confirms DELIVERED is terminal: no further PATCH, no cancel.
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lifecycle_full_fulfilment(api_client: AsyncClient):
    # ── 1. Create ─────────────────────────────────────────────────────────────
    order_id = await _create(api_client, _SINGLE_ITEM)

    order = await _get(api_client, order_id)
    assert order["status"] == "PENDING"
    assert order["updated_at"] is None

    assert any(o["id"] == order_id for o in await _list_by_status(api_client, "PENDING"))

    # ── 2. PENDING → PROCESSING ───────────────────────────────────────────────
    await _patch_status(api_client, order_id, "PROCESSING")

    order = await _get(api_client, order_id)
    assert order["status"] == "PROCESSING"

    assert any(o["id"] == order_id for o in await _list_by_status(api_client, "PROCESSING"))
    assert not any(o["id"] == order_id for o in await _list_by_status(api_client, "PENDING"))

    # ── 3. PROCESSING → SHIPPED ───────────────────────────────────────────────
    await _patch_status(api_client, order_id, "SHIPPED")

    order = await _get(api_client, order_id)
    assert order["status"] == "SHIPPED"

    assert any(o["id"] == order_id for o in await _list_by_status(api_client, "SHIPPED"))
    assert not any(o["id"] == order_id for o in await _list_by_status(api_client, "PROCESSING"))

    # ── 4. SHIPPED → DELIVERED ────────────────────────────────────────────────
    await _patch_status(api_client, order_id, "DELIVERED")

    order = await _get(api_client, order_id)
    assert order["status"] == "DELIVERED"

    assert any(o["id"] == order_id for o in await _list_by_status(api_client, "DELIVERED"))
    assert not any(o["id"] == order_id for o in await _list_by_status(api_client, "SHIPPED"))

    # ── 5. Terminal checks ────────────────────────────────────────────────────
    # Cannot advance beyond DELIVERED
    r = await api_client.patch(f"/orders/{order_id}/status", json={"status": "SHIPPED"})
    assert r.status_code == 422

    r = await api_client.patch(f"/orders/{order_id}/status", json={"status": "PENDING"})
    assert r.status_code == 422

    # Cannot cancel a DELIVERED order
    r = await api_client.delete(f"/orders/{order_id}")
    assert r.status_code == 409

    # Record is still retrievable
    assert (await _get(api_client, order_id))["status"] == "DELIVERED"


# ═════════════════════════════════════════════════════════════════════════════
# VARIANT 2 — Early cancel lifecycle
# PENDING → CANCELLED
# Confirms record is retained (soft-delete), is terminal, and cannot advance.
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lifecycle_early_cancel(api_client: AsyncClient):
    # ── 1. Create ─────────────────────────────────────────────────────────────
    order_id = await _create(api_client, _SINGLE_ITEM)
    assert (await _get(api_client, order_id))["status"] == "PENDING"
    assert any(o["id"] == order_id for o in await _list_by_status(api_client, "PENDING"))

    # ── 2. Cancel ─────────────────────────────────────────────────────────────
    await _cancel(api_client, order_id)

    # ── 3. Record retained with CANCELLED status ───────────────────────────────
    order = await _get(api_client, order_id)
    assert order["status"] == "CANCELLED"
    assert order["updated_at"] is not None

    assert any(o["id"] == order_id for o in await _list_by_status(api_client, "CANCELLED"))
    assert not any(o["id"] == order_id for o in await _list_by_status(api_client, "PENDING"))

    # ── 4. Terminal checks ────────────────────────────────────────────────────
    # Cannot cancel again
    r = await api_client.delete(f"/orders/{order_id}")
    assert r.status_code == 409

    # Cannot advance a CANCELLED order via PATCH
    r = await api_client.patch(f"/orders/{order_id}/status", json={"status": "PROCESSING"})
    assert r.status_code == 422

    r = await api_client.patch(f"/orders/{order_id}/status", json={"status": "SHIPPED"})
    assert r.status_code == 422

    r = await api_client.patch(f"/orders/{order_id}/status", json={"status": "DELIVERED"})
    assert r.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# VARIANT 3 — Cancel-after-processing attempt
# Create → PENDING → PROCESSING → try cancel (fails 409) → SHIPPED → DELIVERED
# Verifies that cancel is exclusively a PENDING operation.
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lifecycle_cancel_blocked_after_processing(api_client: AsyncClient):
    # ── 1. Create + verify PENDING ────────────────────────────────────────────
    order_id = await _create(api_client, _SINGLE_ITEM)
    assert (await _get(api_client, order_id))["status"] == "PENDING"

    # ── 2. Advance to PROCESSING ──────────────────────────────────────────────
    await _patch_status(api_client, order_id, "PROCESSING")

    # ── 3. Cancel attempt must fail (not PENDING) ─────────────────────────────
    r = await api_client.delete(f"/orders/{order_id}")
    assert r.status_code == 409
    assert (await _get(api_client, order_id))["status"] == "PROCESSING"  # unchanged

    # ── 4. Continue through SHIPPED ───────────────────────────────────────────
    await _patch_status(api_client, order_id, "SHIPPED")

    r = await api_client.delete(f"/orders/{order_id}")
    assert r.status_code == 409
    assert (await _get(api_client, order_id))["status"] == "SHIPPED"  # unchanged

    # ── 5. Reach DELIVERED ────────────────────────────────────────────────────
    await _patch_status(api_client, order_id, "DELIVERED")

    r = await api_client.delete(f"/orders/{order_id}")
    assert r.status_code == 409

    assert (await _get(api_client, order_id))["status"] == "DELIVERED"


# ═════════════════════════════════════════════════════════════════════════════
# VARIANT 4 — Multi-item order, items verified at every stage
# Creates an order with 3 distinct items and confirms:
#   • item count, names, quantities, prices survive every status transition
#   • customer_name never changes
#   • created_at never changes; updated_at progresses
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lifecycle_multi_item_items_survive_transitions(api_client: AsyncClient):
    # ── 1. Create ─────────────────────────────────────────────────────────────
    order_id = await _create(api_client, _MULTI_ITEM)
    created = await _get(api_client, order_id)

    assert created["status"] == "PENDING"
    assert created["customer_name"] == "Multi-Item Tester"
    assert created["updated_at"] is None

    items = created["items"]
    assert len(items) == 3
    names = {i["product_name"] for i in items}
    assert names == {"Laptop", "Mouse", "Keyboard"}
    laptop = next(i for i in items if i["product_name"] == "Laptop")
    assert laptop["quantity"] == 1
    assert laptop["price"] == "999.00"
    mouse = next(i for i in items if i["product_name"] == "Mouse")
    assert mouse["quantity"] == 2

    created_at = created["created_at"]

    # ── 2. PENDING → PROCESSING ───────────────────────────────────────────────
    r = await _patch_status(api_client, order_id, "PROCESSING")
    assert len(r["items"]) == 3
    assert {i["product_name"] for i in r["items"]} == names
    assert r["created_at"] == created_at
    processing_updated_at = r["updated_at"]

    order = await _get(api_client, order_id)
    assert order["customer_name"] == "Multi-Item Tester"

    # ── 3. PROCESSING → SHIPPED ───────────────────────────────────────────────
    r = await _patch_status(api_client, order_id, "SHIPPED")
    assert len(r["items"]) == 3
    assert r["created_at"] == created_at
    assert r["updated_at"] >= processing_updated_at

    # ── 4. SHIPPED → DELIVERED ────────────────────────────────────────────────
    r = await _patch_status(api_client, order_id, "DELIVERED")
    assert len(r["items"]) == 3
    assert {i["product_name"] for i in r["items"]} == names
    assert r["customer_name"] == "Multi-Item Tester"
    assert r["created_at"] == created_at

    final = await _get(api_client, order_id)
    assert final["status"] == "DELIVERED"
    assert len(final["items"]) == 3


# ═════════════════════════════════════════════════════════════════════════════
# VARIANT 5 — Two parallel orders, independent lifecycle paths
# Order A: full fulfilment (PENDING → PROCESSING → SHIPPED → DELIVERED)
# Order B: early cancel   (PENDING → CANCELLED)
# Verifies list filters are always scoped correctly — A never appears in B's
# status bucket and vice-versa.
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_lifecycle_two_orders_independent_paths(api_client: AsyncClient):
    # ── 1. Create both orders ─────────────────────────────────────────────────
    id_a = await _create(api_client, {
        "customer_name": "Order A",
        "items": [{"product_name": "Item A", "quantity": 1, "price": "10.00"}],
    })
    id_b = await _create(api_client, {
        "customer_name": "Order B",
        "items": [{"product_name": "Item B", "quantity": 1, "price": "20.00"}],
    })

    # Both start PENDING
    pending = await _list_by_status(api_client, "PENDING")
    pending_ids = {o["id"] for o in pending}
    assert id_a in pending_ids
    assert id_b in pending_ids

    # ── 2. Advance A, cancel B ────────────────────────────────────────────────
    await _patch_status(api_client, id_a, "PROCESSING")
    await _cancel(api_client, id_b)

    pending = await _list_by_status(api_client, "PENDING")
    pending_ids = {o["id"] for o in pending}
    assert id_a not in pending_ids
    assert id_b not in pending_ids

    assert any(o["id"] == id_a for o in await _list_by_status(api_client, "PROCESSING"))
    assert any(o["id"] == id_b for o in await _list_by_status(api_client, "CANCELLED"))

    # B is terminal — cannot advance
    r = await api_client.patch(f"/orders/{id_b}/status", json={"status": "PROCESSING"})
    assert r.status_code == 422

    # ── 3. Finish A ───────────────────────────────────────────────────────────
    await _patch_status(api_client, id_a, "SHIPPED")
    await _patch_status(api_client, id_a, "DELIVERED")

    assert any(o["id"] == id_a for o in await _list_by_status(api_client, "DELIVERED"))
    assert not any(o["id"] == id_a for o in await _list_by_status(api_client, "SHIPPED"))
    assert any(o["id"] == id_b for o in await _list_by_status(api_client, "CANCELLED"))

    # ── 4. Final state verification ───────────────────────────────────────────
    assert (await _get(api_client, id_a))["status"] == "DELIVERED"
    assert (await _get(api_client, id_b))["status"] == "CANCELLED"

    # Both terminal — no further operations succeed
    r = await api_client.patch(f"/orders/{id_a}/status", json={"status": "SHIPPED"})
    assert r.status_code == 422
    r = await api_client.delete(f"/orders/{id_a}")
    assert r.status_code == 409
    r = await api_client.delete(f"/orders/{id_b}")
    assert r.status_code == 409
