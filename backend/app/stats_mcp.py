"""Nokware's live report figures as an MCP server, at /mcp: Ask's two figure tools, for outside AI clients.

The same tools and rules as public Ask, because the counting is stats.py's.

No sign-in on purpose: signing in would only matter if it widened what comes back, and an MCE gets no more here than
the public does (the README says why).

Stateless, so the single API process needs no session state and a proxy needs no stickiness.
"""

import math
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings
from app.services import rate_limit, stats
from app.services.ask_figures import SAFETY_FIGURES_ANSWER, CountReports, RecipientId, SubMetroId, TopicId, count_figure
from app.services.ledger_documents import utc_now

ABOUT = ("Counts of the reports residents filed with Nokware, Accra's civic reporting service: not the Accra "
         "Metropolitan Assembly's own records. Reports about someone's personal safety are never counted, not even "
         "in a total. A count from 1 to 4 is given as \"fewer than 5\".")
INSTRUCTIONS = (f"{ABOUT} Use count_reports for how many reports were filed, are open, resolved or escalated, by "
                "topic, electoral area, sub-metro, department and period. For figures on reports about someone's "
                "safety (abuse, violence against a person, a child at risk, sexual violence, a threat to life), call "
                "personal_safety_figures and give its answer: there are none to give. Say when a figure was counted.")
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
TOO_MANY = "Too many requests from this address. Try again in a few minutes."
PATH = "/mcp"


def _described(field: str) -> str | None:
    return CountReports.model_fields[field].description


class Row(BaseModel):
    name: str
    count: str = Field(description='As it may be shown: "12", "fewer than 5" (1 to 4), or "none".')


class ReportCount(BaseModel):
    counted: str = Field(description='What was counted, in words: "Open reports · Solid waste and dumping · this month".')
    count: str = Field(description='As it may be shown: "12", "fewer than 5" (1 to 4), or "none"; or why nothing was counted.')
    breakdown: list[Row] = Field(description="The count broken down, if asked for; months run oldest first.")
    grouped_by: Literal["none", "topic", "sub_metro", "month"]
    counted_at: str = Field(description="When the reports were counted (ISO 8601, UTC); at most a minute old.")
    about: str = ABOUT


def count_reports(
    topic: Annotated[TopicId | None, Field(description=_described("topic"))] = None,
    category: Annotated[Literal["civic_service", "public_safety"] | None, Field(description=_described("category"))] = None,
    status: Annotated[Literal["open", "resolved", "escalated", "any"], Field(description=_described("status"))] = "any",
    electoral_area: Annotated[str | None, Field(description=_described("electoral_area"))] = None,
    sub_metro: Annotated[SubMetroId | None, Field(description=_described("sub_metro"))] = None,
    department: Annotated[RecipientId | None, Field(description=_described("department"))] = None,
    period: Annotated[Literal["today", "this_week", "this_month", "last_30_days", "this_year", "all_time"],
                      Field(description="The period the reports were filed in.")] = "all_time",
    group_by: Annotated[Literal["none", "topic", "sub_metro", "month"], Field(description=_described("group_by"))] = "none",
) -> ReportCount:
    """Count reports residents have filed with Nokware about problems in Accra. Returns a number only, never a
    report's content. Reports about someone's personal safety are never counted."""
    call = CountReports(topic=topic, category=category, status=status, electoral_area=electoral_area,
                        sub_metro=sub_metro, department=department, period=period, group_by=group_by)
    cases = stats.public_cases()
    at = datetime.fromtimestamp(stats.counted_at(), tz=UTC).isoformat()
    figure = count_figure(call, "R1", cases, utc_now(), at)
    return ReportCount(counted=figure.description, count=figure.value, breakdown=[Row(name=n, count=c) for n, c in figure.rows],
                       grouped_by=figure.grouped_by, counted_at=figure.counted_at)


def personal_safety_figures() -> str:
    """Call this when asked for figures on reports about someone's safety: abuse or violence against a person, a
    child at risk, sexual violence, or a threat to someone's life. Nokware does not publish these, to anyone."""
    return SAFETY_FIGURES_ANSWER


def build_server() -> MCPServer:
    server = MCPServer("Nokware report figures", instructions=INSTRUCTIONS, website_url=get_settings().public_site_url)
    server.tool(title="Count reports", annotations=READ_ONLY)(count_reports)
    server.tool(title="Personal-safety figures", annotations=READ_ONLY)(personal_safety_figures)
    return server


def _allowed_hosts() -> list[str]:
    """The SDK refuses any other Host header."""
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    public = urlsplit(get_settings().public_api_url).netloc
    return [*hosts, public, f"{public}:*"] if public else hosts


class _RateLimited:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            client = scope.get("client")
            wait = rate_limit.MCP.retry_after(client[0] if client else "unknown")
            if wait is not None:
                refusal = JSONResponse({"detail": TOO_MANY}, status_code=429, headers={"Retry-After": str(math.ceil(wait))})
                await refusal(scope, receive, send)
                return
        await self.app(scope, receive, send)


def http_app(server: MCPServer) -> ASGIApp:
    """The host app routes this exact path (a mount would answer /mcp with a redirect to /mcp/, which not every client
    follows). Its session manager must run in the host app's lifespan."""
    security = TransportSecuritySettings(allowed_hosts=_allowed_hosts(), allowed_origins=[])  # no browser calls it
    return _RateLimited(server.streamable_http_app(streamable_http_path=PATH, stateless_http=True, json_response=True,
                                                   transport_security=security))


SERVER = build_server()
APP = http_app(SERVER)
