"""
Create an initial user in the EC-OPS database.

Usage:
    uv run python scripts/seed_user.py
    uv run python scripts/seed_user.py --username admin --password secret123
    uv run python scripts/seed_user.py --username alice --email alice@example.com --password s3cr3t

If no arguments are given, the script uses defaults and prompts for a password
(or uses SEED_PASSWORD env var for non-interactive use).
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values  # noqa: E402

env = dotenv_values(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", env.get("DATABASE_URL", ""))
os.environ.setdefault("JWT_SECRET_KEY", env.get("JWT_SECRET_KEY", "dev"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from src.auth.models import User  # noqa: E402,F401
from src.auth.schemas import UserCreate  # noqa: E402
from src.auth.service import create_user, get_user_by_username  # noqa: E402
from src.core.config import settings  # noqa: E402


async def seed(username: str, password: str, email: str | None) -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        existing = await get_user_by_username(username, session)
        if existing is not None:
            print(f"[skip] User '{username}' already exists (id={existing.id})")
            return
        data = UserCreate(username=username, password=password, email=email)
        user = await create_user(data, session)
        await session.commit()
        print(f"[ok]   Created user '{username}' (id={user.id})")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed an initial EC-OPS user.")
    parser.add_argument("--username", default="admin", help="Username (default: admin)")
    parser.add_argument("--email", default=None, help="Email address (optional)")
    parser.add_argument("--password", default=None, help="Password (prompted if omitted)")
    args = parser.parse_args()

    password = args.password or os.environ.get("SEED_PASSWORD")
    if not password:
        password = getpass.getpass(f"Password for '{args.username}': ")
    if len(password) < 8:
        sys.exit("[error] Password must be at least 8 characters")

    asyncio.run(seed(args.username, password, args.email))


if __name__ == "__main__":
    main()
