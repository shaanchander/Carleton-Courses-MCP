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

## Requirements

- Python 3.14+
- uv
- Network access to Carleton's public course search and RateMyProfessors endpoints

## Setup

From the project root:

```bash
uv sync
```

## Configure Your Client

This server is meant to be started by your MCP client through its JSON config.

(Replace `/absolute/path/to/carleton-courses-mcp` with your local path.)

### For clients that use mcpServers

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
 (You might instead have to provide the full path to uv which can be found with ```which uv``` on Linux and Mac and ```where uv``` on Windows)

## TODO:
	- trim graphql calls
	- cleanup response from course_details and rmp_prof_details (don't waste context)
	- more classes to better format data (ex. profs, course details, etc.)
	- Reddit search?
	- Fetch outlines for certain faculties?
	- Use BeautifulSoup for HTML parsing?