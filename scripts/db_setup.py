"""
Bootstrap EC-OPS databases in one shot.

Usage:
    uv run python scripts/db_setup.py

What it does:
  1. Creates the application and test databases (skips if they exist).
  2. Enables the pgvector extension in both.
  3. Runs Alembic migrations to create all tables.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
env = dotenv_values(ROOT / ".env")

_DEFAULT_DB = "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops"
_DEFAULT_TEST_DB = "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops_test"


def _parse(url: str) -> dict:
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    p = urlparse(url)
    return {
        "host": p.hostname or "localhost",
        "port": p.port or 5432,
        "user": p.username or "postgres",
        "password": p.password or "",
        "database": p.path.lstrip("/"),
    }


async def _create_db_if_missing(sys_conn: asyncpg.Connection, name: str) -> None:
    exists = await sys_conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
    if exists:
        print(f"  [skip] database '{name}' already exists")
    else:
        await sys_conn.execute(f'CREATE DATABASE "{name}"')
        print(f"  [ok]   created database '{name}'")


async def _enable_vector(params: dict) -> None:
    conn = await asyncpg.connect(**params)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        print(f"  [ok]   pgvector enabled in '{params['database']}'")
    finally:
        await conn.close()


async def main() -> None:
    db = _parse(env.get("DATABASE_URL", _DEFAULT_DB))
    test_db = _parse(env.get("TEST_DATABASE_URL", _DEFAULT_TEST_DB))

    sys_params = {**db, "database": "postgres"}

    print("Connecting to PostgreSQL...")
    try:
        sys_conn = await asyncpg.connect(**sys_params)
    except Exception as exc:
        sys.exit(
            f"\nCannot connect to PostgreSQL: {exc}\n"
            "Check that PostgreSQL is running and DATABASE_URL in .env is correct."
        )

    print("\nCreating databases...")
    await _create_db_if_missing(sys_conn, db["database"])
    await _create_db_if_missing(sys_conn, test_db["database"])
    await sys_conn.close()

    print("\nEnabling pgvector...")
    try:
        await _enable_vector(db)
        await _enable_vector({**test_db})
    except Exception as exc:
        sys.exit(
            f"\npgvector extension failed: {exc}\n"
            "Install pgvector for your PostgreSQL version and restart the server."
        )

    print("\nRunning migrations...")
    # Delegate to scripts/migrate.py so all migration logic lives in one place.
    result = subprocess.run(
        ["uv", "run", "python", "scripts/migrate.py"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        sys.exit("\nMigration failed — see output above.")

    print("\n[done] Database ready.")
    print(
        "       Start the server: uv run python -m src.main"
        " --reload_dirs=[\"src\"]"
    )


if __name__ == "__main__":
    asyncio.run(main())
