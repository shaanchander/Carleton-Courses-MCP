# from typing import Any
from helpers import course_search, search_terms, course_details, rmp_prof_details, rmp_prof_search

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
async def request_term_ids() -> dict:
    """
    Available course terms for searching. Returns a dictionary mapping term codes to human-readable names.

    """

    return await search_terms()

@mcp.tool()
async def request_course_details(crn: int, term_id:int) -> dict:
    """
    Available course terms for searching. Returns a dictionary mapping term codes to human-readable names.

    """

    return await course_details(crn, term_id)


@mcp.tool()
async def request_rmp_prof_search(name: str) -> list[dict]:
    """
    Search for professors on RateMyProfessors.com by name. Returns a list of dictionaries containing professor information.

    """

    return await rmp_prof_search(name)

@mcp.tool()
async def request_rmp_prof_details(id: str) -> dict:
    """
    Search for specific professor details on RateMyProfessors.com by professor ID. Returns a dictionary containing detailed professor information.

    """

    return await rmp_prof_details(id)
    

if __name__ == "__main__":
    mcp.run()