"""
One-command setup for EC-OPS.

Usage:
    uv run python scripts/setup.py           # install deps, set up DB
    uv run python scripts/setup.py --start   # same, then start the server
    uv run python scripts/setup.py --help
"""
from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


# ── helpers ──────────────────────────────────────────────────────────────────


def _fail(msg: str) -> None:
    print(f"\n[error] {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"  [ok]   {msg}")


def _skip(msg: str) -> None:
    print(f"  [skip] {msg}")


def _step(msg: str) -> None:
    print(f"\n{msg}")


def _parse_db_url(url: str) -> tuple[str, int]:
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    p = urlparse(url)
    return (p.hostname or "localhost", p.port or 5432)


def _read_env_value(key: str, default: str) -> str:
    env_file = ROOT / ".env"
    source = env_file if env_file.exists() else ROOT / ".env.example"
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line[len(key) + 1 :].strip()
    return default


# ── checks ───────────────────────────────────────────────────────────────────


def check_python() -> None:
    _step("Checking prerequisites...")
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 12):
        _fail(
            f"Python 3.12+ required, found {major}.{minor}.\n"
            "       Install Python 3.12 from https://python.org and retry."
        )
    _ok(f"Python {major}.{minor}")


def check_uv() -> None:
    if not shutil.which("uv"):
        _fail(
            "uv not found on PATH.\n"
            "       Install it with:  pip install uv\n"
            "       Or:               curl -Ls https://astral.sh/uv/install.sh | sh"
        )
    _ok("uv found")


def check_postgres() -> None:
    db_url = _read_env_value(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops",
    )
    host, port = _parse_db_url(db_url)
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError:
        _fail(
            f"Cannot reach PostgreSQL at {host}:{port}.\n"
            "       Make sure PostgreSQL is running and DATABASE_URL in .env is correct.\n"
            "       Run this script first without a .env — it will copy .env.example for you."
        )
    _ok(f"PostgreSQL reachable at {host}:{port}")


# ── setup steps ──────────────────────────────────────────────────────────────


def copy_env() -> None:
    _step("Configuring environment...")
    env = ROOT / ".env"
    example = ROOT / ".env.example"
    if not example.exists():
        _fail(".env.example not found — repository may be incomplete.")
    if env.exists():
        _skip(".env already exists (not overwriting)")
    else:
        shutil.copy(example, env)
        _ok(".env created from .env.example")
        print(
            "\n  ⚠  Open .env and set your PostgreSQL password before continuing.\n"
            "     DATABASE_URL and TEST_DATABASE_URL both need the correct password.\n"
            "     Then re-run this script."
        )
        sys.exit(0)


def sync_deps() -> None:
    _step("Installing dependencies...")
    result = subprocess.run(
        ["uv", "sync", "--extra", "dev"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        _fail("uv sync failed — see output above.")
    _ok("dependencies installed")


def setup_db() -> None:
    _step("Setting up database...")
    result = subprocess.run(
        ["uv", "run", "python", "scripts/db_setup.py"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        _fail("Database setup failed — see output above.")


def seed_user() -> None:
    _step("Creating initial user...")
    import getpass as _getpass
    import os as _os

    seed_password = _os.environ.get("SEED_PASSWORD", "")
    if not seed_password:
        print("  Choose a password for the 'admin' user (min 8 chars).")
        print("  This account is used to obtain JWT tokens for all API calls.\n")
        try:
            seed_password = _getpass.getpass("  Password: ")
        except (KeyboardInterrupt, EOFError):
            print()
            seed_password = "Password1!"
            print(f"  (no input — using default: {seed_password!r})")
    result = subprocess.run(
        ["uv", "run", "python", "scripts/seed_user.py",
         "--username", "admin", "--password", seed_password],
        cwd=ROOT,
    )
    if result.returncode != 0:
        _fail("User seeding failed — see output above.")


def print_guide() -> None:
    base = "http://localhost:8002"
    print(
        f"""
╔══════════════════════════════════════════════════════════════════╗
║                 EC-OPS is ready!                                 ║
╚══════════════════════════════════════════════════════════════════╝

  Server URL : {base}
  Chat UI    : {base}/
  Health     : {base}/health   (public — no auth required)
  API docs   : {base}/docs     (Swagger UI — includes auth)

── Authentication ────────────────────────────────────────────────────
  Every API endpoint except /health requires a JWT Bearer token.

  1. An 'admin' user was created during setup.

  2. Get a token:
       POST {base}/auth/token
         Body (form): username=admin&password=<your password>
         → returns: {{"access_token":"<jwt>","token_type":"bearer"}}

  3. Use the token:
       Authorization: Bearer <jwt>

── REST endpoints ───────────────────────────────────────────────────
  POST   {base}/orders                    Create an order
  GET    {base}/orders                    List all orders
  GET    {base}/orders?status=PENDING     Filter by status
  GET    {base}/orders/{{id}}             Get a single order
  PATCH  {base}/orders/{{id}}/status      Advance order status (state machine)
  DELETE {base}/orders/{{id}}             Cancel a PENDING order

── AI agent ─────────────────────────────────────────────────────────
  GET  {base}/agent/stream?message=…  AG-UI SSE stream
  POST {base}/a2a/tasks/send           A2A task submission

  SSE clients that can't set headers may pass token as query param:
    {base}/agent/stream?message=…&token=<jwt>

  Requires LM Studio running with a loaded model (see README for setup).

  Guardrails fire before every LM Studio call:
    • Messages over 500 chars are rejected
    • Injection patterns (jailbreak, system-prompt extraction, etc.) are blocked
    • Non-order requests are declined with a polite message
  Output is sanitized: UUIDs truncated to 8 chars, tool names hidden,
  stack traces replaced with a generic error message.

── Debug logging ────────────────────────────────────────────────────
  To trace the full LM Studio conversation (request payload, response,
  tool inputs/outputs), add to .env:

    LOG_LEVEL=DEBUG

  This surfaces → LM Studio / ← LM Studio log lines per iteration,
  plus httpx HTTP traffic to localhost:1234. Remove for normal use.

── Tests ─────────────────────────────────────────────────────────────
  Run all 395 tests (no LM Studio required — all tests use mocks):
    uv run pytest tests/ --tb=short

  Run only evaluation tests (guardrails + sanitizer, deterministic):
    uv run pytest tests/ -m eval --tb=short

  Skip evaluation tests:
    uv run pytest tests/ -m "not eval" --tb=short

  VS Code: open the Testing panel (flask icon) — tests are discovered
  automatically. Use Run Configurations (F5) for "Test: All",
  "Test: Eval only", "Test: Skip evals", and "Test: Current file".

── Firing requests ──────────────────────────────────────────────────

  Option A — VS Code / JetBrains HTTP files
    1. Open  requests/auth.http  — run the Login request to get a token
    2. Copy the access_token value from the response
    3. Open the file you want (orders.http, agent.http, etc.) and
       replace  PASTE_ACCESS_TOKEN_HERE  with your token
    4. Run any request

    Files:
      requests/auth.http         Register + login (start here)
      requests/orders.http       REST CRUD
      requests/agent.http        Agent + A2A
      requests/scenarios.http    End-to-end flows
      requests/validation.http   Error cases + 401 tests

    Install the "REST Client" extension (humao.rest-client) in VS Code,
    or use JetBrains' built-in HTTP client.

  Option B — Insomnia collection
    1. Import  requests/EC-OPS.insomnia_collection.json  into Insomnia
       (File → Import → From File).
    2. Select the "EC-OPS Local" sub-environment — baseUrl is pre-set to {base}.
    3. Run  Auth › Login  — the token is saved automatically.
    4. All other requests have Bearer auth pre-wired — ready to fire.

    To regenerate the collection after editing .http files:
      uv run python scripts/generate_insomnia.py

────────────────────────────────────────────────────────────────────
"""
    )


def start_server() -> None:
    _step("Starting server (Ctrl+C to stop)...")
    try:
        subprocess.run(
            ["uv", "run", "python", "-m", "src.main"],
            cwd=ROOT,
            check=True,
        )
    except KeyboardInterrupt:
        print("\nServer stopped.")


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set up and optionally start the EC-OPS server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run python scripts/setup.py           # setup only\n"
            "  uv run python scripts/setup.py --start   # setup then start server\n"
        ),
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start the server after setup completes.",
    )
    args = parser.parse_args()

    print("EC-OPS setup\n" + "=" * 40)

    check_python()
    copy_env()        # exits early on first run to let user fill in .env
    check_uv()
    check_postgres()
    sync_deps()
    setup_db()
    seed_user()
    print_guide()

    if args.start:
        start_server()
    else:
        print("  Run with --start to launch the server, or:")
        print("    uv run python -m src.main\n")


if __name__ == "__main__":
    main()
