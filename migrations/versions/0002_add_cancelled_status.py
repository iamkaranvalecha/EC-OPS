"""add CANCELLED to orderstatus enum

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-21 00:00:00.000000

Adds the CANCELLED value to the orderstatus PostgreSQL enum type to support
soft-delete cancellation with audit trail retention.

Design notes:
    - PostgreSQL 12+ allows ALTER TYPE ... ADD VALUE inside a transaction (the
      old restriction was lifted in PG 12; this project requires PG 16+).
      Do NOT use autocommit_block() — with the asyncpg async migration runner
      (connection.run_sync) it opens a second connection that ignores
      DATABASE_URL and falls back to alembic.ini's placeholder URL, causing
      'type orderstatus does not exist'.

    - The upgrade is written defensively: it checks whether orderstatus exists
      as a PostgreSQL enum before deciding what to do.  This handles the edge
      case where alembic_version records 0001 as applied but the tables were
      later dropped (e.g. by a test's drop_all in a finally block that does not
      touch alembic_version).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    type_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_type WHERE typname = 'orderstatus' AND typtype = 'e'"
        )
    ).scalar()

    if type_exists:
        # Normal path: add CANCELLED to the existing enum.
        cancelled_exists = conn.execute(
            sa.text(
                "SELECT 1 FROM pg_enum e"
                " JOIN pg_type t ON t.oid = e.enumtypid"
                " WHERE t.typname = 'orderstatus' AND e.enumlabel = 'CANCELLED'"
            )
        ).scalar()
        if not cancelled_exists:
            conn.execute(
                sa.text("ALTER TYPE orderstatus ADD VALUE 'CANCELLED'")
            )
    else:
        # Recovery path: orderstatus was never created (or was dropped).
        # Create it fresh with all five values so subsequent migrations work.
        conn.execute(
            sa.text(
                "CREATE TYPE orderstatus AS ENUM"
                " ('PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED')"
            )
        )
        # If the orders table exists but status is TEXT, cast it over.
        orders_exists = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables"
                " WHERE table_schema = 'public' AND table_name = 'orders'"
            )
        ).scalar()
        if orders_exists:
            conn.execute(
                sa.text(
                    "ALTER TABLE orders ALTER COLUMN status"
                    " TYPE orderstatus USING status::orderstatus"
                )
            )


def downgrade() -> None:
    conn = op.get_bind()

    # Revert any CANCELLED orders to PENDING before removing the enum value.
    orders_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables"
            " WHERE table_schema = 'public' AND table_name = 'orders'"
        )
    ).scalar()
    if orders_exists:
        conn.execute(
            sa.text("UPDATE orders SET status = 'PENDING' WHERE status = 'CANCELLED'")
        )

    type_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_type WHERE typname = 'orderstatus' AND typtype = 'e'"
        )
    ).scalar()
    if not type_exists:
        return  # nothing to downgrade

    # PostgreSQL has no DROP VALUE; recreate the type without CANCELLED.
    if orders_exists:
        conn.execute(sa.text("ALTER TABLE orders ALTER COLUMN status TYPE TEXT"))
    conn.execute(sa.text("DROP TYPE orderstatus"))
    conn.execute(
        sa.text(
            "CREATE TYPE orderstatus AS ENUM"
            " ('PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED')"
        )
    )
    if orders_exists:
        conn.execute(
            sa.text(
                "ALTER TABLE orders ALTER COLUMN status TYPE orderstatus"
                " USING status::orderstatus"
            )
        )
