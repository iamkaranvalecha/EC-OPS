"""
Alembic migration runner for EC-OPS.

Usage:
    uv run python scripts/migrate.py               # apply all pending migrations
    uv run python scripts/migrate.py --check       # show state; exit 1 if pending
    uv run python scripts/migrate.py --rollback    # downgrade one revision
    uv run python scripts/migrate.py --help

Can also be imported and called programmatically:
    from scripts.migrate import run_migrations, check_pending
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_alembic(*args: str) -> tuple[int, str]:
    """Run an alembic subcommand. Returns (exit_code, combined stdout+stderr)."""
    result = subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def _detect_and_repair_inconsistency() -> bool:
    """Return True if the database was in an inconsistent state and was repaired.

    Inconsistency: alembic_version records a revision but the core tables are
    missing (e.g. dropped by a test's drop_all that doesn't touch alembic_version).
    Fix: stamp back to base so the next upgrade re-applies all migrations.
    """
    import asyncio

    import asyncpg
    from dotenv import dotenv_values

    env = dotenv_values(ROOT / ".env")
    raw_url = env.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops",
    )
    url = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    async def _check() -> bool:
        try:
            conn = await asyncpg.connect(url)
        except Exception:
            return False  # can't connect — let alembic surface the real error
        try:
            # Is there a recorded revision?
            try:
                row = await conn.fetchrow("SELECT version_num FROM alembic_version LIMIT 1")
            except Exception:
                return False  # no alembic_version table — fresh DB, nothing to repair
            if row is None:
                return False  # no revision recorded, nothing to repair

            # Is the orders table missing?
            orders_exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.tables"
                " WHERE table_schema = 'public' AND table_name = 'orders'"
            )
            return orders_exists is None  # True = inconsistent
        finally:
            await conn.close()

    is_inconsistent = asyncio.run(_check())
    if is_inconsistent:
        print(
            "[warn]  alembic_version has a recorded revision but the 'orders' table\n"
            "        is missing — database is in an inconsistent state.\n"
            "        Stamping back to base so all migrations re-apply cleanly...\n"
        )
        code, out = _run_alembic("stamp", "base")
        if out:
            print(out)
        if code != 0:
            sys.exit(f"[error] Failed to stamp base: {out}")
        print("[ok]   Stamped to base. Migrations will run from 0001.\n")
        return True
    return False


def check_pending(verbose: bool = True) -> bool:
    """Return True if there are pending migrations, False if already at head.

    Prints current revision and whether the schema is up-to-date when verbose=True.
    Exits non-zero on alembic errors.
    """
    code, out = _run_alembic("current")
    if code != 0:
        if verbose:
            print(f"[error] alembic current failed:\n{out}", file=sys.stderr)
        sys.exit(1)
    if verbose:
        print(f"Current revision:\n  {out or '(none — no migrations applied yet)'}\n")

    is_at_head = "(head)" in out
    if verbose:
        if is_at_head:
            print("[ok]   Schema is up to date — no migrations pending.")
        else:
            _, heads = _run_alembic("heads")
            print(f"Pending migrations exist. Head:\n  {heads}")
    return not is_at_head


def run_migrations() -> None:
    """Apply all pending migrations (alembic upgrade head).

    Safe to call when already at head — exits cleanly with no-op message.
    Detects and auto-repairs the case where alembic_version records a revision
    but the actual tables are missing (e.g. dropped by a test's drop_all).
    """
    _detect_and_repair_inconsistency()
    pending = check_pending(verbose=True)
    if not pending:
        return

    print("\nApplying migrations...")
    code, out = _run_alembic("upgrade", "head")
    if out:
        print(out)
    if code != 0:
        sys.exit(f"\n[error] Migration failed (exit {code}) — see output above.")
    print("\n[ok]   All migrations applied.")


def rollback_one() -> None:
    """Downgrade by one revision (alembic downgrade -1)."""
    print("Rolling back one revision...")
    code, out = _run_alembic("downgrade", "-1")
    if out:
        print(out)
    if code != 0:
        sys.exit(f"\n[error] Rollback failed (exit {code}) — see output above.")
    print("\n[ok]   Rolled back one revision.")
    check_pending(verbose=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="EC-OPS Alembic migration runner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run python scripts/migrate.py               # apply pending\n"
            "  uv run python scripts/migrate.py --check       # check state only\n"
            "  uv run python scripts/migrate.py --rollback    # downgrade one step\n"
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="Show current state; exit 1 if pending migrations exist.",
    )
    group.add_argument(
        "--rollback",
        action="store_true",
        help="Downgrade the database by one Alembic revision.",
    )
    args = parser.parse_args()

    print("EC-OPS — Migration\n" + "=" * 40)

    if args.check:
        pending = check_pending(verbose=True)
        sys.exit(1 if pending else 0)
    elif args.rollback:
        rollback_one()
    else:
        run_migrations()


if __name__ == "__main__":
    main()
