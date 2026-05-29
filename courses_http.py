import asyncio
import os
from urllib.parse import parse_qs

import uvicorn
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from helpers import (
    course_details,
    course_search,
    fetch_subject_courses,
    fetch_undergrad_program_info,
    fetch_undergrad_programs,
    rmp_prof_details,
    rmp_prof_ratings_by_course,
    rmp_prof_search,
    search_terms,
)


HTTP_HOST = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("MCP_HTTP_PORT", "8000"))
MCP_HTTP_PATH = os.getenv("MCP_HTTP_PATH", "/mcp")

DEFAULT_QUERYAUTH_USERS = {
    "test-user": "test-pass-123",
}


def parse_queryauth_users(raw: str) -> dict[str, str]:
    """Parse MCP_QUERYAUTH_USERS from 'user:password,user2:password2' format."""
    users: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        username, password = pair.split(":", 1)
        username = username.strip()
        password = password.strip()
        if username and password:
            users[username] = password
    return users


def get_queryauth_users() -> dict[str, str]:
    raw_users = os.getenv("MCP_QUERYAUTH_USERS", "").strip()
    if not raw_users:
        return dict(DEFAULT_QUERYAUTH_USERS)
    parsed = parse_queryauth_users(raw_users)
    return parsed if parsed else dict(DEFAULT_QUERYAUTH_USERS)


class QueryAuthMiddleware:
    """Simple query-param auth for quick local testing.

    Required query parameters:
        - user
        - password
    """

    def __init__(self, app: ASGIApp, mcp_path: str, users: dict[str, str]):
        self.app = app
        self.mcp_path = mcp_path
        self.users = users

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == self.mcp_path or path.startswith(f"{self.mcp_path}/"):
            query_string = scope.get("query_string", b"").decode("utf-8")
            query_params = parse_qs(query_string, keep_blank_values=True)

            user = query_params.get("user", [""])[0]
            password = query_params.get("password", [""])[0]
            expected_password = self.users.get(user)

            if expected_password is None or password != expected_password:
                response = JSONResponse(
                    {
                        "error": "unauthorized",
                        "message": "Missing or invalid query credentials. Use ?user=<user>&password=<password>",
                    },
                    status_code=401,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class CourseSearchRequest(BaseModel):
    subject: str
    code: str


class CourseDetailRequest(BaseModel):
    crn: str
    term_id: int


mcp = FastMCP(
    "Carleton Courses MCP (Query Auth)",
    host=HTTP_HOST,
    port=HTTP_PORT,
    streamable_http_path=MCP_HTTP_PATH,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def request_course_search(course_requests: list[CourseSearchRequest], course_term: int = 202620) -> dict:
    """Fetch course information for a list of (subject, code) requests."""

    results = await asyncio.gather(
        *[course_search(item.subject.upper(), item.code, course_term) for item in course_requests]
    )

    return {f"{item.subject}{item.code}": result for item, result in zip(course_requests, results)}


@mcp.tool()
async def request_term_ids() -> dict:
    """Returns available course terms for searching."""

    return await search_terms()


@mcp.tool()
async def request_course_details(detail_requests: list[CourseDetailRequest]) -> dict:
    """Fetch course details for a list of (crn, term_id) requests."""

    results = await asyncio.gather(
        *[course_details(item.crn, item.term_id) for item in detail_requests]
    )

    return {item.crn: result for item, result in zip(detail_requests, results)}


@mcp.tool()
async def request_rmp_prof_search(search_requests: list[str]) -> dict:
    """Search for professors on RateMyProfessors.com by name."""

    results = await asyncio.gather(*[rmp_prof_search(name) for name in search_requests])

    return {name: result for name, result in zip(search_requests, results)}


@mcp.tool()
async def request_rmp_prof_details(detail_requests: list[str]) -> dict:
    """Fetch RateMyProfessors details for a list of professor IDs."""

    results = await asyncio.gather(*[rmp_prof_details(prof_id) for prof_id in detail_requests])

    return {prof_id: result for prof_id, result in zip(detail_requests, results)}


@mcp.tool()
async def request_rmp_prof_ratings_by_course(prof_id: str, course_codes: list[str]) -> dict:
    """Returns all professor ratings filtered by specific course codes from RMP."""

    return await rmp_prof_ratings_by_course(prof_id, course_codes)


@mcp.tool()
async def request_subject_courses_text(course_subject: str) -> str:
    """Returns all courses for a specified subject (e.g. COMP)."""

    return await fetch_subject_courses(course_subject)


@mcp.tool()
async def request_undergrad_programs() -> list[str]:
    """Returns all undergrad program slugs."""

    return await fetch_undergrad_programs()


@mcp.tool()
async def request_undergrad_program_info(program_slug: str) -> str:
    """Returns all information about a specified undergrad program by slug."""

    return await fetch_undergrad_program_info(program_slug)


if __name__ == "__main__":
    queryauth_users = get_queryauth_users()
    app = mcp.streamable_http_app()
    app = QueryAuthMiddleware(app, mcp_path=MCP_HTTP_PATH, users=queryauth_users)

    print(f"Starting query-auth MCP server on http://{HTTP_HOST}:{HTTP_PORT}{MCP_HTTP_PATH}")
    print("Configured query-auth users:")
    for username in queryauth_users:
        print(f"  - {username}")

    uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT)