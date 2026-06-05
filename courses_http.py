import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import uvicorn


def _load_dotenv() -> None:
    """Load .env file into os.environ (simple, no dependencies)."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from helpers import (
    course_details,
    course_search,
    fetch_academic_year_events,
    fetch_subject_courses,
    fetch_undergrad_program_info,
    fetch_undergrad_programs,
    rmp_prof_details,
    rmp_prof_ratings_by_course,
    rmp_prof_search,
    search_terms,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HTTP_HOST = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("MCP_HTTP_PORT", "8000"))
MCP_HTTP_PATH = os.getenv("MCP_HTTP_PATH", "/")

# Auth mode: "oauth" | "query" (query = local testing only)
AUTH_MODE = os.getenv("MCP_AUTH_MODE", "oauth")

# Base URL for OAuth redirects & metadata (e.g. https://mcp.yourdomain.com)
BASE_URL = os.getenv("MCP_BASE_URL", "").rstrip("/")

# JWT signing secret — change this! Rotate periodically.
JWT_SECRET = os.getenv("MCP_JWT_SECRET", "change-me-now")
JWT_EXPIRE_SECONDS = int(os.getenv("MCP_JWT_EXPIRE_SECONDS", "3600"))  # 1h

# Auth users for /authorize login form (username:password)
# Set via MCP_AUTH_USERS="user:pass,user2:pass2"
AUTH_USERS: dict[str, str] = {}
for _pair in os.getenv("MCP_AUTH_USERS", "admin:changeme").split(","):
    _pair = _pair.strip()
    if ":" in _pair:
        _u, _p = _pair.split(":", 1)
        AUTH_USERS[_u.strip()] = _p.strip()

# Fallback query auth for local testing
DEFAULT_QUERYAUTH_USERS = {
    "test-user": "test-pass-123",
}

# Browser-based MCP clients send CORS preflight requests before Streamable HTTP.
CORS_ALLOW_ORIGINS = ["*"]
CORS_ALLOW_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]
CORS_EXPOSE_HEADERS = ["Mcp-Session-Id", "WWW-Authenticate"]

# ---------------------------------------------------------------------------
# In-memory stores (ephemeral — fine for personal use)
# ---------------------------------------------------------------------------
auth_codes: dict[str, dict] = {}  # code → {client_id, redirect_uri, state, code_challenge, ...}

# ---------------------------------------------------------------------------
# Rate limiter (sliding window per IP)
# ---------------------------------------------------------------------------
# Max requests per window for OAuth endpoints
RATE_LIMIT_MAX = int(os.getenv("MCP_RATE_LIMIT_MAX", "30"))
RATE_LIMIT_WINDOW = int(os.getenv("MCP_RATE_LIMIT_WINDOW", "60"))  # seconds

_rate_buckets: dict[str, list[float]] = {}  # ip → [timestamps]


def _check_rate_limit(ip: str) -> bool:
    """Return True if under limit. False if rate-limited."""
    now = time.time()
    if ip not in _rate_buckets:
        _rate_buckets[ip] = []
    # Prune old entries
    _rate_buckets[ip] = [t for t in _rate_buckets[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_buckets[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_buckets[ip].append(now)
    return True


def _get_client_ip(scope: Scope) -> str:
    headers = _get_headers(scope)
    # Check Cloudflare CF-Connecting-IP first, then fallback
    return headers.get("cf-connecting-ip", scope.get("client", ("unknown",))[0])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_headers(scope: Scope) -> dict[str, str]:
    headers = {}
    for key, value in scope.get("headers", []):
        headers[key.decode("latin-1").lower()] = value.decode("latin-1")
    return headers


def _pkce_challenge(code_verifier: str, method: str = "S256") -> str:
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    else:
        digest = code_verifier.encode("ascii")
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _b64decode_unpadded(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _create_jwt(subject: str, client_id: str, resource: str | None = None) -> str:
    """Create a simple HS256 JWT (no library needed)."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "client_id": client_id,
        "iat": now,
        "exp": now + JWT_EXPIRE_SECONDS,
        "jti": str(uuid.uuid4()),
    }
    if resource:
        payload["aud"] = resource
    h_b64 = urlsafe_b64encode(json.dumps(header, separators=(',', ':')).encode()).rstrip(b"=").decode()
    p_b64 = urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).rstrip(b"=").decode()
    signing_input = f"{h_b64}.{p_b64}"
    signature = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    s_b64 = urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{signing_input}.{s_b64}"


def _verify_jwt(token: str) -> dict | None:
    """Verify HS256 JWT, return payload or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}"
        expected_sig = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
        actual_sig = _b64decode_unpadded(parts[2])
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64decode_unpadded(parts[1]))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def parse_queryauth_users(raw: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        username, password = pair.split(":", 1)
        if username.strip() and password.strip():
            users[username.strip()] = password.strip()
    return users


def get_queryauth_users() -> dict[str, str]:
    raw = os.getenv("MCP_QUERYAUTH_USERS", "").strip()
    parsed = parse_queryauth_users(raw) if raw else {}
    return parsed or dict(DEFAULT_QUERYAUTH_USERS)


def _login_form(error: str | None) -> str:
    """Render a clean HTML login form for the /authorize endpoint."""
    error_html = f'<p style="color:#dc2626;font-size:0.875rem;margin:0 0 1rem;text-align:center">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MCP Server Login</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f3f4f6;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
  }}
  .card {{
    background: #fff;
    padding: 2rem 2.5rem;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1), 0 4px 12px rgba(0,0,0,0.05);
    width: 100%;
    max-width: 360px;
  }}
  h1 {{
    font-size: 1.25rem;
    font-weight: 600;
    color: #111827;
    margin-bottom: 1.5rem;
    text-align: center;
  }}
  label {{
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
    margin-bottom: 0.375rem;
  }}
  input[type="text"], input[type="password"] {{
    width: 100%;
    padding: 0.625rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 0.9375rem;
    outline: none;
    transition: border-color 0.15s;
  }}
  input:focus {{
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
  }}
  .field {{ margin-bottom: 1rem; }}
  button {{
    width: 100%;
    padding: 0.6875rem;
    background: #111827;
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    margin-top: 0.5rem;
    transition: background 0.15s;
  }}
  button:hover {{ background: #1f2937; }}
</style>
</head>
<body>
  <form class="card" method="post">
    <h1>MCP Server Login</h1>
    {error_html}
    <div class="field">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" required autocomplete="username" autofocus>
    </div>
    <div class="field">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required autocomplete="current-password">
    </div>
    <button type="submit">Sign in</button>
  </form>
</body>
</html>"""


# ---------------------------------------------------------------------------
# OAuth 2.1 Authorization Server (minimal, login form)
# ---------------------------------------------------------------------------
class OAuthServerMiddleware:
    """Minimal OAuth 2.1 server: /authorize, /token, /register + Bearer validation.

    Supports PKCE S256, dynamic client registration, and HS256 JWTs.
    """

    def __init__(self, app: ASGIApp, base_url: str, mcp_path: str):
        self.app = app
        self.base_url = base_url.rstrip("/")
        self.mcp_path = mcp_path if mcp_path.startswith("/") else f"/{mcp_path}"
        if len(self.mcp_path) > 1:
            self.mcp_path = self.mcp_path.rstrip("/")
        self.resource_url = (
            self.base_url if self.mcp_path == "/" else f"{self.base_url}{self.mcp_path}"
        )
        self.resource_metadata_url = f"{self.base_url}/.well-known/oauth-protected-resource"

    # ---- Route table ----
    OAUTH_PATHS = {
        "/.well-known/oauth-authorization-server": "_metadata",
        "/.well-known/oauth-protected-resource": "_resource_metadata",
        "/authorize": "_authorize",
        "/token": "_token",
        "/register": "_register",
    }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Rate limit on OAuth + MCP endpoints
        if path in self.OAUTH_PATHS or self._is_mcp_path(path):
            ip = _get_client_ip(scope)
            if not _check_rate_limit(ip):
                response = JSONResponse(
                    {"error": "too_many_requests", "error_description": "Rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
                )
                await response(scope, receive, send)
                return

        # 1. OAuth endpoints
        if path in self.OAUTH_PATHS:
            handler = getattr(self, self.OAUTH_PATHS[path])
            await handler(scope, receive, send)
            return

        # 2. MCP endpoint — require Bearer token
        if self._is_mcp_path(path):
            headers = _get_headers(scope)
            auth_header = headers.get("authorization", "")

            if not auth_header.startswith("Bearer "):
                response = JSONResponse(
                    {"error": "unauthorized", "error_description": "Bearer token required"},
                    status_code=401,
                    headers={
                        "WWW-Authenticate": (
                            'Bearer '
                            f'resource_metadata="{self.resource_metadata_url}", '
                            'scope="mcp"'
                        )
                    },
                )
                await response(scope, receive, send)
                return

            token = auth_header[7:].strip()
            payload = _verify_jwt(token)
            if not payload:
                response = JSONResponse(
                    {"error": "unauthorized", "error_description": "Invalid or expired token"},
                    status_code=401,
                    headers={
                        "WWW-Authenticate": (
                            'Bearer error="invalid_token", '
                            f'resource_metadata="{self.resource_metadata_url}", '
                            'scope="mcp"'
                        )
                    },
                )
                await response(scope, receive, send)
                return

            logger.info("Authenticated MCP request from client_id=%s", payload.get("client_id"))

        # 3. Pass through
        await self.app(scope, receive, send)

    def _is_mcp_path(self, path: str) -> bool:
        if self.mcp_path == "/":
            return path == "/"
        return path == self.mcp_path or path.startswith(f"{self.mcp_path}/")

    def _valid_resource(self, resource: str) -> bool:
        return not resource or resource in {self.resource_url, self.base_url}

    # ---- Endpoints ----
    async def _metadata(self, scope: Scope, receive: Receive, send: Send) -> None:
        metadata = {
            "issuer": self.base_url,
            "authorization_endpoint": f"{self.base_url}/authorize",
            "token_endpoint": f"{self.base_url}/token",
            "registration_endpoint": f"{self.base_url}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "resource_parameter_supported": True,
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": ["mcp"],
        }
        response = JSONResponse(metadata, status_code=200)
        await response(scope, receive, send)

    async def _resource_metadata(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Protected resource metadata for OAuth discovery."""
        metadata = {
            "resource": self.resource_url,
            "authorization_servers": [self.base_url],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["mcp"],
            "token_endpoint_auth_methods_supported": ["none"],
        }
        response = JSONResponse(metadata, status_code=200)
        await response(scope, receive, send)

    async def _authorize(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Authorization endpoint — login form, then redirect with code."""
        query = scope.get("query_string", b"").decode("utf-8")
        params = parse_qs(query, keep_blank_values=True)

        response_type = params.get("response_type", [""])[0]
        if response_type != "code":
            response = JSONResponse({"error": "unsupported_response_type"}, status_code=400)
            await response(scope, receive, send)
            return

        client_id = params.get("client_id", [""])[0]
        redirect_uri = params.get("redirect_uri", [""])[0]
        state = params.get("state", [""])[0]
        code_challenge = params.get("code_challenge", [""])[0]
        code_challenge_method = params.get("code_challenge_method", ["S256"])[0]
        resource = params.get("resource", [""])[0]

        if not client_id or not redirect_uri:
            response = JSONResponse({"error": "invalid_request"}, status_code=400)
            await response(scope, receive, send)
            return
        if code_challenge_method != "S256":
            response = JSONResponse({"error": "invalid_request", "error_description": "S256 PKCE required"}, status_code=400)
            await response(scope, receive, send)
            return
        if not self._valid_resource(resource):
            response = JSONResponse({"error": "invalid_target", "error_description": "Unknown resource"}, status_code=400)
            await response(scope, receive, send)
            return

        # POST = login form submission
        if scope["method"] == "POST":
            body_b = b""
            while True:
                msg = await receive()
                if msg["type"] == "http.request":
                    body_b += msg.get("body", b"")
                if not msg.get("more_body", False):
                    break
            form = parse_qs(body_b.decode("utf-8"))
            username = form.get("username", [""])[0]
            password = form.get("password", [""])[0]

            if username not in AUTH_USERS or AUTH_USERS[username] != password:
                html = _login_form(error="Invalid credentials")
                response = Response(content=html, status_code=200, media_type="text/html")
                await response(scope, receive, send)
                return

            logger.info("OAuth authorize approved for user=%s", username)
            code = str(uuid.uuid4())
            auth_codes[code] = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "resource": resource or self.resource_url,
                "created_at": time.time(),
            }
            redirect_params = {"code": code}
            if state:
                redirect_params["state"] = state
            redirect_url = f"{redirect_uri}?{urlencode(redirect_params)}"
            response = RedirectResponse(redirect_url, status_code=302)
            await response(scope, receive, send)
            return

        # GET = show login form
        html = _login_form(error=None)
        response = Response(content=html, status_code=200, media_type="text/html")
        await response(scope, receive, send)
        return

    async def _token(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Token endpoint — exchange code + code_verifier for access token."""
        if scope["method"] != "POST":
            response = JSONResponse({"error": "method_not_allowed"}, status_code=405)
            await response(scope, receive, send)
            return

        # Read body
        body_b = b""
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                body_b += msg.get("body", b"")
            if not msg.get("more_body", False):
                break

        # Parse form data
        body = body_b.decode("utf-8")
        params = parse_qs(body, keep_blank_values=True)

        grant_type = params.get("grant_type", [""])[0]
        if grant_type != "authorization_code":
            response = JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
            await response(scope, receive, send)
            return

        code = params.get("code", [""])[0]
        code_verifier = params.get("code_verifier", [""])[0]
        redirect_uri = params.get("redirect_uri", [""])[0]
        resource = params.get("resource", [""])[0]

        if not code or code not in auth_codes:
            response = JSONResponse({"error": "invalid_grant"}, status_code=400)
            await response(scope, receive, send)
            return

        auth_info = auth_codes.pop(code)  # single-use
        if resource and resource != auth_info.get("resource"):
            response = JSONResponse({"error": "invalid_target", "error_description": "Resource mismatch"}, status_code=400)
            await response(scope, receive, send)
            return

        # Verify PKCE
        expected_challenge = auth_info["code_challenge"]
        if expected_challenge:
            method = auth_info["code_challenge_method"]
            actual_challenge = _pkce_challenge(code_verifier, method)
            if actual_challenge != expected_challenge:
                response = JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)
                await response(scope, receive, send)
                return

        # Verify redirect_uri matches
        if redirect_uri and redirect_uri != auth_info["redirect_uri"]:
            response = JSONResponse({"error": "invalid_grant"}, status_code=400)
            await response(scope, receive, send)
            return

        # Issue tokens
        access_token = _create_jwt("user", auth_info["client_id"], auth_info.get("resource"))
        refresh_token = str(uuid.uuid4())

        response = JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": JWT_EXPIRE_SECONDS,
            "refresh_token": refresh_token,
        }, status_code=200)
        await response(scope, receive, send)

    async def _register(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Dynamic client registration — auto-approve."""
        if scope["method"] != "POST":
            response = JSONResponse({"error": "method_not_allowed"}, status_code=405)
            await response(scope, receive, send)
            return

        # Read body
        body_b = b""
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                body_b += msg.get("body", b"")
            if not msg.get("more_body", False):
                break

        try:
            data = json.loads(body_b)
        except (json.JSONDecodeError, ValueError):
            response = JSONResponse({"error": "invalid_request"}, status_code=400)
            await response(scope, receive, send)
            return

        client_id = str(uuid.uuid4())
        redirect_uris = data.get("redirect_uris", [])

        logger.info("Registered new OAuth client: %s", client_id)

        response = JSONResponse({
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "client_secret_expires_at": 0,  # public client, no secret
            "redirect_uris": redirect_uris,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        }, status_code=201)
        await response(scope, receive, send)


# ---------------------------------------------------------------------------
# Legacy query-param auth (local testing)
# ---------------------------------------------------------------------------
class QueryAuthMiddleware:
    """Simple query-param auth for local testing ONLY. NOT for production."""

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
                    {"error": "unauthorized", "message": "Invalid query credentials"},
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


@mcp.tool()
async def request_academic_year_events(terms: list[str]) -> dict:
    """
    Returns academic year calendar events for the requested terms.

    Use this when a user asks about specific dates or needs to know a calendar deadline,
    such as when registration opens or closes, when tuition is due, when classes start,
    or other term-specific academic deadlines.

    Input format: pass a list of term strings in the form "Summer 2026", "Fall 2026",
    or "Winter 2027". The season must be one of Summer, Fall, or Winter, followed by a
    space and the year.
    """

    return await fetch_academic_year_events(terms)

def create_app() -> ASGIApp:
    """Build ASGI app with auth middleware based on MCP_AUTH_MODE."""
    app = mcp.streamable_http_app()

    if AUTH_MODE == "oauth":
        if not BASE_URL:
            raise ValueError(
                "MCP_BASE_URL required for oauth mode. "
                "Set it to your public URL (e.g. https://mcp.yourdomain.com)"
            )
        app = OAuthServerMiddleware(app, base_url=BASE_URL, mcp_path=MCP_HTTP_PATH)
        logger.info("Auth mode: OAuth 2.1 (login form, PKCE S256)")
        logger.info("OAuth metadata at: %s/.well-known/oauth-authorization-server", BASE_URL)

    elif AUTH_MODE == "query":
        queryauth_users = get_queryauth_users()
        app = QueryAuthMiddleware(app, mcp_path=MCP_HTTP_PATH, users=queryauth_users)
        logger.warning("Auth mode: query params (LOCAL TESTING ONLY - credentials in URL)")
        logger.info("Configured users: %s", list(queryauth_users.keys()))

    else:
        raise ValueError(f"Unknown MCP_AUTH_MODE={AUTH_MODE!r}. Use 'oauth' or 'query'.")

    return CORSMiddleware(
        app,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=["*"],
        expose_headers=CORS_EXPOSE_HEADERS,
    )


if __name__ == "__main__":
    app = create_app()

    print(f"Starting MCP server on http://{HTTP_HOST}:{HTTP_PORT}{MCP_HTTP_PATH}")
    print(f"Auth mode: {AUTH_MODE}")
    if AUTH_MODE == "oauth":
        print(f"Base URL: {BASE_URL}")
        print(f"JWT secret: {'SET' if JWT_SECRET != 'change-me-now' else 'DEFAULT - CHANGE MCP_JWT_SECRET!'}")

    uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT)
