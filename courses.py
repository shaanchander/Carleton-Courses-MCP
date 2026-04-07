# from typing import Any
from helpers import course_search, search_terms

import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("Carleton Courses MCP")

@mcp.tool()
async def request_course_info(course_subject: str, course_code: str = "", course_term = 202620) -> dict:
    """Fetch course information based on subject and optional course code.
    Args:
        course_subject (str): The subject of the course (e.g., "COMP").
        course_code (str, optional): The specific course code (e.g., "1405"). Defaults to "".
    """

    return await course_search(course_subject, course_code, course_term)


@mcp.tool()
async def request_available_terms() -> dict:
    """
    Available course terms for searching. Returns a dictionary mapping term codes to human-readable names.

    """

    return await search_terms()
    

if __name__ == "__main__":
    mcp.run()