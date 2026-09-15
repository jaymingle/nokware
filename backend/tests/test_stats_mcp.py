"""The MCP server: public Ask's two figure tools and rules, read-only, no sign-in, rate-limited; never safety figures."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client
from starlette.applications import Starlette
from starlette.routing import Route

from app import stats_mcp
from app.services import rate_limit, stats
from app.services.ask_figures import SAFETY_FIGURES_ANSWER
from app.services.rate_limit import RateLimit
from tests.test_ask_figures import SAFETY, case

JSON_RPC = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def cases(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Six open waste reports, one resolved, and two about someone's safety."""
    held = [*[case() for _ in range(6)], case(status="resolved"), SAFETY, SAFETY]
    monkeypatch.setattr(stats, "public_cases", lambda: held)
    monkeypatch.setattr(stats, "counted_at", lambda: 1_789_000_000.0)
    return held


@pytest.mark.anyio
async def test_it_offers_ask_s_two_tools_read_only_with_no_safety_topic() -> None:
    async with Client(stats_mcp.build_server(), raise_exceptions=True) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == {"count_reports", "personal_safety_figures"}
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in tools.values())
    topics = tools["count_reports"].input_schema["properties"]["topic"]
    assert "solid_waste" in str(topics) and "abuse" not in str(topics)


@pytest.mark.anyio
async def test_a_count_follows_the_public_rules(cases: list[dict[str, Any]]) -> None:
    async with Client(stats_mcp.build_server(), raise_exceptions=True) as client:
        everything = (await client.call_tool("count_reports", {})).structured_content
        resolved = (await client.call_tool("count_reports", {"status": "resolved"})).structured_content
        by_topic = (await client.call_tool("count_reports", {"group_by": "topic"})).structured_content
        safety_topic = await client.call_tool("count_reports", {"topic": "abuse"})
        refusal = await client.call_tool("personal_safety_figures", {})
    assert everything and everything["count"] == "7" and "never counted" in everything["about"]  # safety is in no total
    assert resolved and resolved["count"] == "fewer than 5"
    assert by_topic and by_topic["breakdown"] == [{"name": "Solid waste and dumping", "count": "7"}]
    assert safety_topic.is_error  # not a topic it knows
    assert refusal.content[0].text == SAFETY_FIGURES_ANSWER  # type: ignore[union-attr]


@asynccontextmanager
async def _running(app: Starlette) -> AsyncIterator[None]:
    async with app.state.server.session_manager.run():
        yield


@pytest.fixture
def http() -> Iterator[TestClient]:
    """The server at /mcp as main.py routes it, with its session manager running."""
    server = stats_mcp.build_server()
    app = Starlette(routes=[Route(stats_mcp.PATH, endpoint=stats_mcp.http_app(server))], lifespan=_running)
    app.state.server = server
    with TestClient(app, base_url="http://localhost") as client:
        yield client


def _call(client: TestClient, **headers: str) -> Any:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "count_reports", "arguments": {}}}
    return client.post("/mcp", json=body, headers={**JSON_RPC, **headers}, follow_redirects=False)


def test_over_http_it_answers_at_mcp_without_sign_in_and_only_for_its_own_host(http: TestClient, cases: list[dict[str, Any]]) -> None:
    answer = _call(http)
    assert answer.status_code == 200 and answer.json()["result"]["structuredContent"]["count"] == "7"
    assert _call(http, Host="evil.example").status_code == 421  # DNS rebinding: another Host is refused
    assert _call(http, Origin="https://nokware.tstitagency.com").status_code == 403  # for MCP clients, not web pages


def test_a_flood_is_refused(http: TestClient, cases: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rate_limit, "MCP", RateLimit(limit=2, window_seconds=600))
    assert [_call(http).status_code for _ in range(3)] == [200, 200, 429]
