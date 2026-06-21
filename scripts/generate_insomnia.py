"""
Generate an Insomnia v4 collection from all .http files in requests/.

Usage:
    uv run python scripts/generate_insomnia.py

Output:
    requests/EC-OPS.insomnia_collection.json  (single file — workspace + env + requests)

Import into Insomnia: File → Import → From File.

Workflow after import:
  1. Select the "EC-OPS Local" sub-environment (top-left dropdown).
  2. Run Auth › Login — {{ token }} is saved automatically via after-response script.
  3. All other requests have Bearer auth pre-wired — ready to fire.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUESTS_DIR = ROOT / "requests"
OUTPUT = REQUESTS_DIR / "EC-OPS.insomnia_collection.json"
BASE_URL_DEFAULT = "http://localhost:8002"

# Insomnia template-tag syntax (spaces required)
_BASE_URL_VAR = "{{ baseUrl }}"

_PUBLIC_PATHS: frozenset[str] = frozenset({"/auth/token", "/auth/register", "/health"})
_LOGIN_PATH = "/auth/token"
_LOGIN_METHOD = "POST"

# After-response script saved on the login request — runs when Insomnia receives the response
_TOKEN_SAVE_SCRIPT = (
    "const data = await response.json();\n"
    "if (data && data.access_token) {\n"
    "    await insomnia.environment.set('token', data.access_token);\n"
    "    console.log('EC-OPS: token saved');\n"
    "}"
)


def _uid(prefix: str = "res") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _to_insomnia_var(text: str) -> str:
    """Convert {{varName}} (Postman) → {{ varName }} (Insomnia) in any string."""
    return re.sub(r"\{\{(\w+)\}\}", r"{{ \1 }}", text)


@dataclass
class HttpRequest:
    name: str
    method: str
    url: str
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: str | None = None


def parse_http_file(path: Path) -> list[HttpRequest]:
    """Parse a VS Code REST Client .http file into HttpRequest objects."""
    lines = path.read_text(encoding="utf-8").splitlines()

    file_vars: dict[str, str] = {}
    for line in lines:
        m = re.match(r"^@(\w+)\s*=\s*(.+)$", line.strip())
        if m:
            key, val = m.group(1), m.group(2).strip()
            file_vars[key] = _BASE_URL_VAR if key == "baseUrl" else val

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

        method, raw_url = m.group(1), m.group(2)

        # Substitute file-level vars, then normalize to Insomnia template syntax
        url = raw_url
        for k, v in file_vars.items():
            url = url.replace(f"{{{{{k}}}}}", v)
        url = _to_insomnia_var(url)

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


def _url_path(url: str) -> str:
    """Extract the bare path portion from an Insomnia-template URL."""
    path = url
    if path.startswith(_BASE_URL_VAR):
        path = path[len(_BASE_URL_VAR):]
    if "?" in path:
        path = path.split("?", 1)[0]
    path = re.sub(r"\{\{.*?\}\}", "", path).rstrip("/")
    return path or "/"


def _is_public(req: HttpRequest) -> bool:
    return _url_path(req.url) in _PUBLIC_PATHS


def _is_login(req: HttpRequest) -> bool:
    return req.method == _LOGIN_METHOD and _url_path(req.url) == _LOGIN_PATH


def _insomnia_request(req: HttpRequest, parent_id: str) -> dict:
    """Build one Insomnia request resource."""
    # Strip Authorization from headers — auth is handled by the authentication block
    headers = []
    for k, v in req.headers:
        if k.lower() == "authorization":
            continue
        headers.append({"id": _uid("hdr"), "name": k, "value": v})

    auth = {"type": "none"} if _is_public(req) else {
        "type": "bearer",
        "token": "{{ token }}",
        "prefix": "Bearer",
    }

    body: dict = {}
    if req.body:
        content_type = next(
            (v for k, v in req.headers if k.lower() == "content-type"), ""
        )
        if "application/x-www-form-urlencoded" in content_type:
            params = []
            for pair in req.body.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params.append({"id": _uid("par"), "name": k, "value": v})
            body = {"mimeType": "application/x-www-form-urlencoded", "params": params}
        else:
            body = {"mimeType": "application/json", "text": req.body}

    resource: dict = {
        "_id": _uid("req"),
        "_type": "request",
        "parentId": parent_id,
        "name": req.name,
        "method": req.method,
        "url": req.url,
        "headers": headers,
        "authentication": auth,
        "body": body,
    }

    if _is_login(req):
        resource["afterResponseScript"] = _TOKEN_SAVE_SCRIPT

    return resource


def build_collection(http_dir: Path) -> dict:
    http_files = sorted(http_dir.glob("*.http"))
    if not http_files:
        raise FileNotFoundError(f"No .http files found in {http_dir}")

    wrk_id = _uid("wrk")
    env_base_id = _uid("env")
    env_local_id = _uid("env")

    resources: list[dict] = [
        {
            "_id": wrk_id,
            "_type": "workspace",
            "parentId": None,
            "name": "EC-OPS",
            "description": (
                "E-Commerce Order Processing System.\n\n"
                "Getting started:\n"
                "1. Select the 'EC-OPS Local' sub-environment.\n"
                f"2. Run Auth › Login — baseUrl defaults to {BASE_URL_DEFAULT}.\n"
                "3. The {{ token }} variable is saved automatically."
            ),
        },
        {
            "_id": env_base_id,
            "_type": "environment",
            "parentId": wrk_id,
            "name": "Base Environment",
            "data": {},
        },
        {
            "_id": env_local_id,
            "_type": "environment",
            "parentId": env_base_id,
            "name": "EC-OPS Local",
            "data": {
                "baseUrl": BASE_URL_DEFAULT,
                "token": "",
            },
        },
    ]

    for path in http_files:
        reqs = parse_http_file(path)
        if not reqs:
            continue
        folder_name = path.stem.replace("_", " ").replace("-", " ").title()
        fld_id = _uid("fld")
        resources.append({
            "_id": fld_id,
            "_type": "request_group",
            "parentId": wrk_id,
            "name": folder_name,
        })
        for req in reqs:
            resources.append(_insomnia_request(req, fld_id))

    return {
        "_type": "export",
        "__export_format": 4,
        "__export_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "__export_source": "ec-ops-generator",
        "resources": resources,
    }


def main() -> None:
    collection = build_collection(REQUESTS_DIR)
    OUTPUT.write_text(json.dumps(collection, indent=2), encoding="utf-8")

    req_count = sum(1 for r in collection["resources"] if r["_type"] == "request")
    fld_count = sum(1 for r in collection["resources"] if r["_type"] == "request_group")
    print(
        f"[ok] Generated {OUTPUT.relative_to(ROOT)}\n"
        f"     {fld_count} folders · {req_count} requests\n"
        f"     Import: Insomnia > File > Import > From File"
    )


if __name__ == "__main__":
    main()
