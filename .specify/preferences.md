# Confirmed stack preferences — shared across features

language:           Python 3.12
framework:          FastAPI
testing:            pytest + pytest-asyncio + httpx
linting:            ruff
package_manager:    uv

database:           PostgreSQL (SQLAlchemy async ORM + asyncpg driver)
auth:               JWT Bearer tokens (HS256) — python-jose[cryptography] + bcrypt (passlib removed)
deployment_target:  local only

api_style:          REST + SSE (Server-Sent Events for AG-UI streaming)

# test_strategy: unit        = mock all external deps (fast, no infra)
#                integration = real test DB/services per test
#                both        = unit tests for logic + one integration test per major flow
test_strategy: both

# ── Naming & folder conventions ──────────────────────────────────────────────

# file_naming: snake_case → order_service.py, order_router.py
file_naming:        snake_case

# folder_structure: feature-based
#   src/orders/       ← models, service, router
#   src/agent/        ← MCP server, A2A handler, AG-UI stream
#   src/scheduler/    ← APScheduler setup
#   src/core/         ← config, database, dependencies
folder_structure:   feature-based

source_root:        src

# test_location: tests/ mirrors src/ structure
test_location:      tests/

variable_naming:    snake_case
class_naming:       PascalCase
constant_naming:    UPPER_SNAKE_CASE
api_routes:         /kebab-case
db_naming:          snake_case

# ── Agentic / Protocol layer ─────────────────────────────────────────────────

mcp_sdk:            mcp (official Python SDK)
a2a_style:          FastAPI routes implementing Google A2A spec
agui_transport:     Server-Sent Events (GET /agent/stream)
a2ui_style:         CustomEvent blocks embedded in AG-UI stream (type: ui_action)
ai_model:           claude-sonnet-4-6
chat_frontend:      Minimal HTML/JS (frontend/index.html, no build step)
background_jobs:    APScheduler (in-process, FastAPI lifespan)
