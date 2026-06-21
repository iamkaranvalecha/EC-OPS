"""
Generate a Postman Collection v2.1 from all .http files in requests/.

Usage:
    uv run python scripts/generate_postman.py

Output:
    requests/EC-OPS.postman_collection.json      — import into Postman
    requests/EC-OPS.postman_environment.json     — import as "EC-OPS Local" environment

Re-run whenever .http files change to keep the collection in sync.

Postman workflow after import:
  1. Select the "EC-OPS Local" environment from the environment picker.
  2. Run Auth / Login — the token is saved automatically to {{token}}.
  3. All other requests are ready to fire (auth header pre-populated).
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUESTS_DIR = ROOT / "requests"
OUTPUT = REQUESTS_DIR / "EC-OPS.postman_collection.json"
ENVIRONMENT_OUTPUT = REQUESTS_DIR / "EC-OPS.postman_environment.json"
BASE_URL_VAR = "{{baseUrl}}"
BASE_URL_DEFAULT = "http://localhost:8002"

# Paths that never need a Bearer token
_PUBLIC_PATHS: frozenset[str] = frozenset({"/auth/token", "/auth/register", "/health"})

# The login endpoint — gets a post-response script that saves the token
_LOGIN_PATH = "/auth/token"
_LOGIN_METHOD = "POST"

_TOKEN_SAVE_SCRIPT: list[str] = [
    "var data = pm.response.json();",
    "if (data && data.access_token) {",
    "    pm.environment.set('token', data.access_token);",
    "    pm.collectionVariables.set('token', data.access_token);",
    "    console.log('token saved:', data.access_token.slice(0, 20) + '...');",
    "}",
]


@dataclass
class HttpRequest:
    name: str
    method: str
    url: str
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: str | None = None


def _substitute_vars(text: str, vars: dict[str, str]) -> str:
    """Replace @varName and {{varName}} placeholders."""
    for k, v in vars.items():
        text = text.replace(f"@{k}", v)
        text = text.replace(f"{{{{{k}}}}}", v)
    return text


def parse_http_file(path: Path) -> list[HttpRequest]:
    """Parse a VS Code REST Client .http file into a list of HttpRequest objects."""
    lines = path.read_text(encoding="utf-8").splitlines()

    # Collect file-level variable definitions (@key = value)
    file_vars: dict[str, str] = {}
    for line in lines:
        m = re.match(r"^@(\w+)\s*=\s*(.+)$", line.strip())
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key == "baseUrl":
                file_vars[key] = BASE_URL_VAR
            else:
                file_vars[key] = val

    requests: list[HttpRequest] = []
    i = 0
    current_name: str | None = None

    while i < len(lines):
        line = lines[i]

        if line.startswith("###"):
            label = line[3:].strip()
            current_name = label if label else None
            i += 1
            continue

        if re.match(r"^@\w+\s*=", line.strip()) or not line.strip():
            i += 1
            continue

        m = re.match(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)", line.strip())
        if not m:
            i += 1
            continue

        method = m.group(1)
        raw_url = m.group(2)

        url = raw_url
        for k, v in file_vars.items():
            url = url.replace(f"{{{{{k}}}}}", v)

        i += 1
        headers: list[tuple[str, str]] = []
        while i < len(lines):
            h = lines[i]
            if not h.strip() or h.startswith("###") or re.match(
                r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+", h
            ):
                break
            hm = re.match(r"^([^:]+):\s*(.+)$", h)
            if hm:
                headers.append((hm.group(1).strip(), hm.group(2).strip()))
            i += 1

        body_lines: list[str] = []
        if i < len(lines) and not lines[i].strip():
            i += 1
            while i < len(lines):
                bl = lines[i]
                if bl.startswith("###") or re.match(
                    r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+", bl
                ):
                    break
                body_lines.append(bl)
                i += 1

        raw_body = "\n".join(body_lines).strip()
        body = raw_body if raw_body else None

        name = current_name or f"{method} {url}"
        requests.append(HttpRequest(name=name, method=method, url=url, headers=headers, body=body))
        current_name = None

    return requests


def _postman_url(raw: str) -> dict:
    """Convert a raw URL string into Postman URL object."""
    if "?" in raw:
        path_part, query_part = raw.split("?", 1)
    else:
        path_part, query_part = raw, ""

    stripped = path_part
    if stripped.startswith(BASE_URL_VAR):
        stripped = stripped[len(BASE_URL_VAR):]
    path_segments = [s for s in stripped.strip("/").split("/") if s]

    query: list[dict] = []
    if query_part:
        for pair in query_part.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                query.append({"key": k, "value": v})
            else:
                query.append({"key": pair, "value": ""})

    obj: dict = {
        "raw": raw,
        "host": ["{{baseUrl}}"],
        "path": path_segments,
    }
    if query:
        obj["query"] = query
    return obj


def _url_path(url: str) -> str:
    """Extract the bare path from a URL like {{baseUrl}}/auth/token?foo=bar."""
    path = url
    if path.startswith(BASE_URL_VAR):
        path = path[len(BASE_URL_VAR):]
    if "?" in path:
        path = path.split("?", 1)[0]
    # Drop trailing path-variable segments like /{{orderId}}
    path = path.split("{{")[0].rstrip("/")
    return path or "/"


def _is_public(req: HttpRequest) -> bool:
    path = _url_path(req.url)
    return path in _PUBLIC_PATHS


def _is_login(req: HttpRequest) -> bool:
    return req.method == _LOGIN_METHOD and _url_path(req.url) == _LOGIN_PATH


def _postman_item(req: HttpRequest) -> dict:
    """Convert an HttpRequest to a Postman item dict (pure conversion, no enrichment)."""
    headers = []
    for k, v in req.headers:
        # Normalize stale placeholder to the Postman variable
        if k.lower() == "authorization" and "PASTE_ACCESS_TOKEN_HERE" in v:
            v = "Bearer {{token}}"
        headers.append({"key": k, "value": v})

    item: dict = {
        "name": req.name,
        "request": {
            "method": req.method,
            "header": headers,
            "url": _postman_url(req.url),
        },
        "response": [],
    }

    if req.body:
        content_type = next(
            (v for k, v in req.headers if k.lower() == "content-type"), ""
        )
        if "application/x-www-form-urlencoded" in content_type:
            # Emit proper urlencoded key-value pairs instead of raw JSON
            pairs = []
            for pair in req.body.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    pairs.append({"key": k, "value": v, "type": "text"})
            item["request"]["body"] = {"mode": "urlencoded", "urlencoded": pairs}
        else:
            item["request"]["body"] = {
                "mode": "raw",
                "raw": req.body,
                "options": {"raw": {"language": "json"}},
            }

    return item


def _enrich_item(item: dict, req: HttpRequest) -> dict:
    """Inject auth header and login event script after pure conversion."""
    # Inject Authorization on protected routes that don't already have it
    if not _is_public(req):
        has_auth = any(h["key"].lower() == "authorization" for h in item["request"]["header"])
        if not has_auth:
            item["request"]["header"].append(
                {"key": "Authorization", "value": "Bearer {{token}}"}
            )

    # Login endpoint: save access_token to environment + collection variables
    if _is_login(req):
        item["event"] = [
            {
                "listen": "test",
                "script": {
                    "type": "text/javascript",
                    "exec": _TOKEN_SAVE_SCRIPT,
                },
            }
        ]

    return item


def build_collection(http_dir: Path) -> dict:
    http_files = sorted(http_dir.glob("*.http"))
    if not http_files:
        raise FileNotFoundError(f"No .http files found in {http_dir}")

    folders: list[dict] = []
    for path in http_files:
        reqs = parse_http_file(path)
        if not reqs:
            continue
        folder_name = path.stem.replace("_", " ").replace("-", " ").title()
        items = [_enrich_item(_postman_item(r), r) for r in reqs]
        folders.append({"name": folder_name, "item": items})

    return {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": "EC-OPS",
            "description": (
                "E-Commerce Order Processing System — REST API, AI agent, and A2A endpoints.\n\n"
                "**Getting started:**\n"
                "1. Import `EC-OPS.postman_environment.json` and select **EC-OPS Local**.\n"
                f"2. Run **Auth › Login** — `baseUrl` defaults to `{BASE_URL_DEFAULT}`.\n"
                "3. The `{{token}}` variable is saved automatically — all other requests are ready."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "baseUrl", "value": BASE_URL_DEFAULT, "type": "string"},
            {"key": "token",   "value": "",               "type": "string"},
        ],
        "item": folders,
    }


def build_environment() -> dict:
    """Build a Postman environment with baseUrl and token pre-declared."""
    return {
        "name": "EC-OPS Local",
        "_postman_variable_scope": "environment",
        "values": [
            {"key": "baseUrl", "value": BASE_URL_DEFAULT, "type": "default", "enabled": True},
            {"key": "token",   "value": "",               "type": "default", "enabled": True},
        ],
    }


def main() -> None:
    collection = build_collection(REQUESTS_DIR)
    OUTPUT.write_text(json.dumps(collection, indent=2), encoding="utf-8")

    environment = build_environment()
    ENVIRONMENT_OUTPUT.write_text(json.dumps(environment, indent=2), encoding="utf-8")

    item_count = sum(len(f.get("item", [])) for f in collection["item"])
    folder_count = len(collection["item"])
    print(
        f"[ok] Generated {OUTPUT.relative_to(ROOT)}\n"
        f"     {ENVIRONMENT_OUTPUT.relative_to(ROOT)}\n"
        f"     {folder_count} folders · {item_count} requests"
    )


if __name__ == "__main__":
    main()
