# from typing import Any
from helpers import course_search

import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("Carleton Courses MCP")

@mcp.tool()
async def request_course_info(course_subject: str, course_code: str = "") -> dict:
    """Fetch course information based on subject and optional course code.
    Args:
        course_subject (str): The subject of the course (e.g., "COMP").
        course_code (str, optional): The specific course code (e.g., "1405"). Defaults to "".
    """
    
    return course_search(course_subject, course_code)

if __name__ == "__main__":
    mcp.run()