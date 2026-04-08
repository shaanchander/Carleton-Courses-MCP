# from typing import Any
from helpers import course_search, search_terms, course_details, rmp_prof_details, rmp_prof_search

import asyncio
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Carleton Courses MCP")

@mcp.tool()
async def request_course_search(course_requests: list[tuple[str, str]], course_term=202620) -> dict:
    """Fetch course information for a list of (subject, code) requests.
    Args:
        course_requests (list[tuple[str, str]]): A list of (subject, code) tuples.
        course_term (int, optional): Term used for all requests (ALWAYS call request_term_ids before this to know which term to search, don't guess).
    """

    results = await asyncio.gather(
        *[course_search(subject.upper(), code, course_term) for subject, code in course_requests]
    )

    return {f"{subject}{code}": result for (subject, code), result in zip(course_requests, results)}


@mcp.tool()
async def request_term_ids() -> dict:
    """
    Returns available course terms for searching. Returns a dictionary mapping term codes to human-readable names.

    """

    return await search_terms()

@mcp.tool()
async def request_course_details(detail_requests: list[tuple[str, int]]) -> dict:
    """
    Fetch course details for a list of (crn, term_id) requests. CRNs are unique identifiers for specific course offerings in a given term which can
    be obtained from either the user or request_course_search. Term IDs can be obtained from request_term_ids. Returns a dictionary keyed by CRN.

    """

    results = await asyncio.gather(
        *[course_details(crn, term_id) for crn, term_id in detail_requests]
    )

    return {crn: result for (crn, _term_id), result in zip(detail_requests, results)}


@mcp.tool()
async def request_rmp_prof_search(search_requests: list[tuple[str]]) -> dict:
    """
    Search for professors on RateMyProfessors.com by name.
    Accepts a list of one-item tuples: [(name,), ...].
    Returns a dictionary keyed by professor name.

    """

    results = await asyncio.gather(
        *[rmp_prof_search(name) for (name,) in search_requests]
    )

    return {name: result for (name,), result in zip(search_requests, results)}

@mcp.tool()
async def request_rmp_prof_details(detail_requests: list[tuple[str]]) -> dict:
    """
    Search for specific professor details on RateMyProfessors.com by professor ID. Professor scores and details
    are important for students when choosing courses.
    Accepts a list of one-item tuples: [(id,), ...].
    Returns a dictionary keyed by professor ID.

    """

    results = await asyncio.gather(
        *[rmp_prof_details(prof_id) for (prof_id,) in detail_requests]
    )

    return {prof_id: result for (prof_id,), result in zip(detail_requests, results)}
    

if __name__ == "__main__":
    mcp.run()