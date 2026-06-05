# Carleton Courses MCP

An MCP server for querying Carleton University course information, academic calendar dates, undergraduate program data, and RateMyProfessors data.

## Data Sources

- Carleton public course search
- Carleton undergraduate calendar
- Carleton academic year calendar
- RateMyProfessors GraphQL API

## Requirements

- Python 3.14+
- uv
- Network access to the public Carleton and RateMyProfessors endpoints

## Setup

```bash
uv sync
```

## Server Entry Points

| File | Transport | Use case |
| ---- | --------- | -------- |
| `courses.py` | stdio | Local MCP clients such as Claude Desktop, Cursor, or LM Studio |
| `courses_http.py` | Streamable HTTP | Remote MCP clients or local HTTP testing |

## Tools

Both servers expose:

- `request_term_ids` - list available Carleton course search terms.
- `request_course_search` - search for courses by subject, code, and term.
- `request_course_details` - fetch detailed course information by CRN and term.
- `request_rmp_prof_search` - search for Carleton professors on RateMyProfessors.
- `request_rmp_prof_details` - fetch RateMyProfessors details for a professor ID.
- `request_rmp_prof_ratings_by_course` - fetch professor ratings filtered by course code.
- `request_subject_courses_text` - fetch undergraduate calendar course text for a subject.
- `request_undergrad_programs` - list undergraduate program slugs.
- `request_undergrad_program_info` - fetch undergraduate calendar information for a program slug.
- `request_academic_year_events` - fetch academic year calendar events for terms such as `Fall 2026`.

The stdio server also exposes `registration_terminology_resource`, a static set of Carleton registration terminology definitions.

## Stdio Usage

Run directly:

```bash
uv run courses.py
```

Example MCP client config:

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

## HTTP Usage

`courses_http.py` supports two auth modes:

- `oauth` - default; intended for remote clients behind HTTPS.
- `query` - simple query-parameter auth for local testing only.

Start the HTTP server in OAuth mode:

```bash
MCP_BASE_URL=https://mcp.yourdomain.com \
MCP_AUTH_USERS="admin:use-a-real-password" \
MCP_JWT_SECRET="use-a-long-random-secret" \
uv run courses_http.py
```

Start the HTTP server in local query-auth mode:

```bash
MCP_AUTH_MODE=query uv run courses_http.py
```

By default, the HTTP server binds to `0.0.0.0:8000` and serves MCP at `/`.

## HTTP Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `MCP_AUTH_MODE` | `oauth` | Auth mode: `oauth` or `query`. |
| `MCP_HTTP_HOST` | `0.0.0.0` | HTTP bind host. |
| `MCP_HTTP_PORT` | `8000` | HTTP bind port. |
| `MCP_HTTP_PATH` | `/` | Streamable HTTP MCP endpoint path. |
| `MCP_BASE_URL` | unset | Public HTTPS base URL. Required in OAuth mode. |
| `MCP_AUTH_USERS` | `admin:changeme` | Comma-separated `username:password` pairs for OAuth login. |
| `MCP_JWT_SECRET` | `change-me-now` | HS256 JWT signing secret. Change this before exposing the server. |
| `MCP_JWT_EXPIRE_SECONDS` | `3600` | OAuth access token lifetime in seconds. |
| `MCP_QUERYAUTH_USERS` | `test-user:test-pass-123` | Comma-separated `username:password` pairs for query-auth mode. |
| `MCP_RATE_LIMIT_MAX` | `30` | Max requests per rate-limit window for OAuth and MCP endpoints. |
| `MCP_RATE_LIMIT_WINDOW` | `60` | Rate-limit window in seconds. |

`courses_http.py` also loads a local `.env` file from the project root if present.
