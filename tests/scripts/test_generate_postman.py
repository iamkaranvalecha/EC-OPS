"""Tests for the Insomnia v4 collection generator (scripts/generate_insomnia.py)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from scripts.generate_insomnia import (
    BASE_URL_DEFAULT,
    HttpRequest,
    _insomnia_request,
    _is_login,
    _is_public,
    _to_insomnia_var,
    _uid,
    build_collection,
    parse_http_file,
)

# ── fixtures ──────────────────────────────────────────────────────────────────

SIMPLE_HTTP = textwrap.dedent("""\
    ### Simple fixture
    @baseUrl = http://localhost:8002

    ### Health check
    GET {{baseUrl}}/health

    ###

    ### Create order
    POST {{baseUrl}}/orders
    Content-Type: application/json

    {
      "customer_name": "Test",
      "items": [{"product_name": "Widget", "quantity": 1, "price": "9.99"}]
    }
""")

QUERY_HTTP = textwrap.dedent("""\
    @baseUrl = http://localhost:8002

    ### List PENDING
    GET {{baseUrl}}/orders?status=PENDING
""")

LOGIN_HTTP = textwrap.dedent("""\
    @baseUrl = http://localhost:8002

    ### Login
    POST {{baseUrl}}/auth/token
    Content-Type: application/x-www-form-urlencoded

    username=admin&password=Password1!
""")

PROTECTED_HTTP = textwrap.dedent("""\
    @baseUrl = http://localhost:8002

    ### List orders
    GET {{baseUrl}}/orders

    ### Health
    GET {{baseUrl}}/health
""")


@pytest.fixture
def simple_http_file(tmp_path: Path) -> Path:
    f = tmp_path / "simple.http"
    f.write_text(SIMPLE_HTTP, encoding="utf-8")
    return f


@pytest.fixture
def query_http_file(tmp_path: Path) -> Path:
    f = tmp_path / "query.http"
    f.write_text(QUERY_HTTP, encoding="utf-8")
    return f


# ── _to_insomnia_var ──────────────────────────────────────────────────────────


def test_to_insomnia_var_converts_postman_syntax() -> None:
    assert _to_insomnia_var("{{baseUrl}}/orders") == "{{ baseUrl }}/orders"


def test_to_insomnia_var_converts_multiple_vars() -> None:
    result = _to_insomnia_var("{{baseUrl}}/orders/{{orderId}}")
    assert result == "{{ baseUrl }}/orders/{{ orderId }}"


def test_to_insomnia_var_leaves_plain_text_unchanged() -> None:
    assert _to_insomnia_var("http://localhost:8002/health") == "http://localhost:8002/health"


# ── parse_http_file ───────────────────────────────────────────────────────────


def test_parse_method_and_url(simple_http_file: Path) -> None:
    reqs = parse_http_file(simple_http_file)
    assert len(reqs) == 2
    assert reqs[0].method == "GET"
    assert reqs[0].url == "{{ baseUrl }}/health"


def test_parse_replaces_base_url_with_insomnia_var(simple_http_file: Path) -> None:
    reqs = parse_http_file(simple_http_file)
    for r in reqs:
        assert "localhost:8002" not in r.url
        assert "{{ baseUrl }}" in r.url


def test_parse_request_name(simple_http_file: Path) -> None:
    reqs = parse_http_file(simple_http_file)
    assert reqs[0].name == "Health check"
    assert reqs[1].name == "Create order"


def test_parse_headers(simple_http_file: Path) -> None:
    reqs = parse_http_file(simple_http_file)
    assert ("Content-Type", "application/json") in reqs[1].headers


def test_parse_json_body(simple_http_file: Path) -> None:
    reqs = parse_http_file(simple_http_file)
    assert reqs[1].body is not None
    body = json.loads(reqs[1].body)
    assert body["customer_name"] == "Test"


def test_parse_get_has_no_body(simple_http_file: Path) -> None:
    assert parse_http_file(simple_http_file)[0].body is None


def test_parse_query_string(query_http_file: Path) -> None:
    reqs = parse_http_file(query_http_file)
    assert "status=PENDING" in reqs[0].url


# ── _is_public / _is_login ────────────────────────────────────────────────────


def test_health_is_public() -> None:
    req = HttpRequest("Health", "GET", "{{ baseUrl }}/health")
    assert _is_public(req)


def test_auth_token_is_public() -> None:
    req = HttpRequest("Login", "POST", "{{ baseUrl }}/auth/token")
    assert _is_public(req)


def test_auth_register_is_public() -> None:
    req = HttpRequest("Register", "POST", "{{ baseUrl }}/auth/register")
    assert _is_public(req)


def test_orders_is_not_public() -> None:
    req = HttpRequest("List", "GET", "{{ baseUrl }}/orders")
    assert not _is_public(req)


def test_is_login_true() -> None:
    req = HttpRequest("Login", "POST", "{{ baseUrl }}/auth/token")
    assert _is_login(req)


def test_is_login_false_for_get() -> None:
    req = HttpRequest("Get token", "GET", "{{ baseUrl }}/auth/token")
    assert not _is_login(req)


# ── _insomnia_request ─────────────────────────────────────────────────────────


def test_protected_request_gets_bearer_auth() -> None:
    req = HttpRequest("List orders", "GET", "{{ baseUrl }}/orders")
    item = _insomnia_request(req, _uid("fld"))
    assert item["authentication"]["type"] == "bearer"
    assert item["authentication"]["token"] == "{{ token }}"


def test_public_request_has_no_auth() -> None:
    req = HttpRequest("Health", "GET", "{{ baseUrl }}/health")
    item = _insomnia_request(req, _uid("fld"))
    assert item["authentication"]["type"] == "none"


def test_login_item_has_after_response_script() -> None:
    req = HttpRequest(
        "Login", "POST", "{{ baseUrl }}/auth/token",
        headers=[("Content-Type", "application/x-www-form-urlencoded")],
        body="username=admin&password=Password1!",
    )
    item = _insomnia_request(req, _uid("fld"))
    assert "afterResponseScript" in item
    script = item["afterResponseScript"]
    assert "insomnia.environment.set" in script
    assert "access_token" in script


def test_non_login_item_has_no_after_response_script() -> None:
    req = HttpRequest("List orders", "GET", "{{ baseUrl }}/orders")
    item = _insomnia_request(req, _uid("fld"))
    assert "afterResponseScript" not in item


def test_json_body_uses_json_mimeType() -> None:
    req = HttpRequest(
        "Create", "POST", "{{ baseUrl }}/orders",
        headers=[("Content-Type", "application/json")],
        body='{"customer_name": "X", "items": []}',
    )
    item = _insomnia_request(req, _uid("fld"))
    assert item["body"]["mimeType"] == "application/json"
    assert "customer_name" in item["body"]["text"]


def test_form_body_uses_urlencoded_mimeType() -> None:
    req = HttpRequest(
        "Login", "POST", "{{ baseUrl }}/auth/token",
        headers=[("Content-Type", "application/x-www-form-urlencoded")],
        body="username=admin&password=Password1!",
    )
    item = _insomnia_request(req, _uid("fld"))
    assert item["body"]["mimeType"] == "application/x-www-form-urlencoded"
    keys = [p["name"] for p in item["body"]["params"]]
    assert "username" in keys and "password" in keys


def test_authorization_header_stripped_from_headers() -> None:
    """Authorization is handled via authentication block, not headers."""
    req = HttpRequest(
        "List", "GET", "{{ baseUrl }}/orders",
        headers=[("Authorization", "Bearer {{ token }}"), ("Accept", "application/json")],
    )
    item = _insomnia_request(req, _uid("fld"))
    header_names = [h["name"].lower() for h in item["headers"]]
    assert "authorization" not in header_names
    assert "accept" in header_names


# ── build_collection ──────────────────────────────────────────────────────────


def test_build_collection_export_format(tmp_path: Path) -> None:
    (tmp_path / "test.http").write_text(SIMPLE_HTTP, encoding="utf-8")
    col = build_collection(tmp_path)
    assert col["_type"] == "export"
    assert col["__export_format"] == 4


def test_build_collection_has_workspace(tmp_path: Path) -> None:
    (tmp_path / "test.http").write_text(SIMPLE_HTTP, encoding="utf-8")
    col = build_collection(tmp_path)
    workspaces = [r for r in col["resources"] if r["_type"] == "workspace"]
    assert len(workspaces) == 1
    assert workspaces[0]["name"] == "EC-OPS"


def test_build_collection_has_local_environment(tmp_path: Path) -> None:
    (tmp_path / "test.http").write_text(SIMPLE_HTTP, encoding="utf-8")
    col = build_collection(tmp_path)
    envs = [r for r in col["resources"] if r["_type"] == "environment"]
    local = next((e for e in envs if e["name"] == "EC-OPS Local"), None)
    assert local is not None
    assert local["data"]["baseUrl"] == BASE_URL_DEFAULT
    assert local["data"]["token"] == ""


def test_build_collection_groups_by_file(tmp_path: Path) -> None:
    (tmp_path / "orders.http").write_text(SIMPLE_HTTP, encoding="utf-8")
    (tmp_path / "agent.http").write_text(QUERY_HTTP, encoding="utf-8")
    col = build_collection(tmp_path)
    folder_names = [r["name"] for r in col["resources"] if r["_type"] == "request_group"]
    assert "Orders" in folder_names
    assert "Agent" in folder_names


def test_build_collection_no_http_files_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_collection(tmp_path)


def test_build_collection_all_requests_use_base_url_var(tmp_path: Path) -> None:
    (tmp_path / "test.http").write_text(SIMPLE_HTTP, encoding="utf-8")
    col = build_collection(tmp_path)
    reqs = [r for r in col["resources"] if r["_type"] == "request"]
    for req in reqs:
        assert "localhost:8002" not in req["url"], f"Hardcoded URL in {req['name']}"


def test_build_collection_login_gets_token_script(tmp_path: Path) -> None:
    (tmp_path / "auth.http").write_text(LOGIN_HTTP, encoding="utf-8")
    col = build_collection(tmp_path)
    reqs = [r for r in col["resources"] if r["_type"] == "request"]
    login = next((r for r in reqs if "Login" in r["name"]), None)
    assert login is not None
    assert "afterResponseScript" in login
    assert "insomnia.environment.set" in login["afterResponseScript"]


def test_build_collection_protected_has_bearer(tmp_path: Path) -> None:
    (tmp_path / "orders.http").write_text(PROTECTED_HTTP, encoding="utf-8")
    col = build_collection(tmp_path)
    reqs = [r for r in col["resources"] if r["_type"] == "request"]
    orders_req = next(r for r in reqs if "List orders" in r["name"])
    assert orders_req["authentication"]["type"] == "bearer"


def test_build_collection_health_has_no_auth(tmp_path: Path) -> None:
    (tmp_path / "orders.http").write_text(PROTECTED_HTTP, encoding="utf-8")
    col = build_collection(tmp_path)
    reqs = [r for r in col["resources"] if r["_type"] == "request"]
    health = next(r for r in reqs if "Health" in r["name"])
    assert health["authentication"]["type"] == "none"
