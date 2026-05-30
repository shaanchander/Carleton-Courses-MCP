# Carleton Course Search MCP

MCP server for querying Carleton University course data, with professor lookup via RateMyProfessors (RMP).

## Background

This project makes Carleton course information available through MCP tools so it can be used directly by an MCP-compatible client.

Data sources:

- Carleton public course search pages
- RateMyProfessors GraphQL endpoint

## Available Tools

The server in [courses.py](courses.py) exposes:

- request_term_ids (fetch availble terms for search)
- request_course_search (fetch courses with specified subject, code, and term)
- request_course_details (fetch details about a specific course CRN)
- request_rmp_prof_search (search for Carleton University professor by name)
- request_rmp_prof_details (fetch details about a specific professor ID)
- request_rmp_prof_ratings_by_course (fetch all ratings for specific prof filtered by certain course codes)
- request_academic_year_events (fetch academic year calendar events for specified terms)

## Available Resources

The server also exposes a static resource with Carleton registration terminology definitions:

- `carleton://registration-terminology`

## Requirements

- Python 3.14+
- uv
- Network access to Carleton's public course search and RateMyProfessors endpoints

## Setup

From the project root:

```bash
uv sync
```

## Modes

| Mode | Env | Use case | Auth |
|------|-----|----------|------|
| **Stdio** | `uv run courses.py` | Local MCP clients (Claude Desktop, Cursor, etc.) | None |
| **HTTP + Query** | `MCP_AUTH_MODE=query uv run courses_http.py` | Local testing behind tunnel | Query params (`?user=&password=`) |
| **HTTP + Cloudflare** | `MCP_AUTH_MODE=cloudflare uv run courses_http.py` (default) | Remote LLM providers | Cloudflare Access headers |

## Configure Your Client

This server is meant to be started by your MCP client through its JSON config.

(Replace `/absolute/path/to/carleton-courses-mcp` with your local path.)

### For clients that use mcpServers (Stdio)

Use this in your client config (ex. Claude Desktop, LM Studio, etc.):

```json
{
	"mcpServers": {
		"carleton-courses": {
			"command": "uv",
			"args": [
				"--directory",
				"/absolute/path/to/carleton-courses-mcp",
				"run",
				"courses.py"
			]
		}
	}
}
```

### For remote HTTP clients (Claude, ChatGPT, etc.)

Deploy with Cloudflare Access + Tunnel so remote providers can authenticate via OAuth.

#### 1. Start the HTTP server

```bash
# Prod mode (default, requires Cloudflare Access)
MCP_AUTH_MODE=cloudflare uv run courses_http.py

# Local testing mode (query-param auth, NOT for production)
MCP_AUTH_MODE=query uv run courses_http.py
```

Server bind `127.0.0.1:8000` by default. Override with `MCP_HTTP_HOST` / `MCP_HTTP_PORT`.

#### 2. Create Cloudflare Tunnel

```bash
# Install
brew install cloudflared

# Login & create tunnel
cloudflared tunnel login
cloudflared tunnel create mcp-tunnel

# Point domain at tunnel
cloudflared tunnel route dns mcp-tunnel mcp.yourdomain.com

# Run tunnel (maps your domain → localhost:8000)
cloudflared tunnel run --url http://127.0.0.1:8000 mcp-tunnel
```

Now `https://mcp.yourdomain.com/mcp` route to your server. TLS handle by Cloudflare. No open ports needed.

#### 3. Configure Cloudflare Access

**Zero Trust dashboard → Access → Applications → Add an application**:

- **Application name**: `Carleton MCP`
- **Service type**: Self-hosted
- **Domain**: `mcp.yourdomain.com`
- **Public URL**: `mcp.yourdomain.com/*`

Create policy:

- **Policy name**: `Allow authenticated users`
- **Include → Email address** → `email_is_set` is `true`
- Or add identity provider (Google, GitHub, etc.) for real user auth

Save. Cloudflare inject `Cf-Access-Authenticated-User-Email` header on authorized requests.

#### 4. Add to remote LLM provider

Point MCP server URL to `https://mcp.yourdomain.com/mcp`.

Provider send first request → get 401 → trigger OAuth flow → user login via Cloudflare Access → subsequent requests include auth header → authorized.

#### Environment variables

| Var | Default | Description |
|-----|---------|-------------|
| `MCP_AUTH_MODE` | `cloudflare` | `cloudflare` or `query` |
| `MCP_HTTP_HOST` | `127.0.0.1` | Bind address |
| `MCP_HTTP_PORT` | `8000` | Bind port |
| `MCP_HTTP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_QUERYAUTH_USERS` | `test-user:test-pass-123` | Comma-sep `user:pass` pairs (query mode only) |

## TODO:
	- trim graphql calls
	- cleanup response from course_details and rmp_prof_details (don't waste context)
	- more classes to better format data (ex. profs, course details, etc.)
	- Reddit search?
	- Fetch outlines for certain faculties?
	- Use BeautifulSoup for HTML parsing?
	- allow for auto installing into Claude Desktop with one command
	- add ability to search by subject and level (ex. COMP 2000 level)
	- improve docstring for tools (prompts)