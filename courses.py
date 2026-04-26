# from typing import Any
from helpers import (
    course_search,
    search_terms,
    course_details,
    rmp_prof_details,
    rmp_prof_search,
    rmp_prof_ratings_by_course,
    fetch_subject_courses,
    fetch_undergrad_programs,
    fetch_undergrad_program_info,
)

import asyncio
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Carleton Courses MCP")

@mcp.tool()
async def request_course_search(course_requests: list[tuple[str, str]], course_term=202620) -> dict:
    """Fetch course information for a list of (subject, code) requests. This tool can be used to search for an unlimited number of courses at once, 
    which is more efficient than calling request_course_search multiple times for individual courses. (*** GROUP REQUESTS TOGETHER, don't make a bunch of requests for
    a single course, for example, make one query for all courses that you need at once ***)
    Returns a dictionary keyed by "SUBJECTCODE" (e.g. "COMP1406"). If the course is not found, it will return an empty list at the results key.
    Always call request_term_ids first to know which term to search, don't guess.
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
    *** You should NEVER call this more than once per session (the info is static). ***

    """

    return await search_terms()

@mcp.tool()
async def request_course_details(detail_requests: list[tuple[str, int]]) -> dict:
    """
    Fetch course details for a list of (crn, term_id) requests. CRNs are unique identifiers for specific course offerings in a given term which can
    be obtained from either the user or request_course_search. Term IDs can be obtained from request_term_ids. Returns a dictionary keyed by CRN.
    This tool can take an unlimited number of (crn, term_id) requests at once, which is more efficient than calling request_course_details multiple times for individual courses. 
    Always call request_term_ids first to know which term to search, don't guess.

    """

    results = await asyncio.gather(
        *[course_details(crn, term_id) for crn, term_id in detail_requests]
    )

    return {crn: result for (crn, _term_id), result in zip(detail_requests, results)}


@mcp.tool()
async def request_rmp_prof_search(search_requests: list[tuple[str]]) -> dict:
    """
    Search for professors on RateMyProfessors.com by name. Professor scores and details are important for students 
    when choosing courses. This tool can take an unlimited number of professor name requests at once, which is more 
    efficient than calling request_rmp_prof_search multiple times for individual professors. 
    Always call request_rmp_prof_search before request_rmp_prof_details to get professor IDs, don't guess.
    Accepts a list of one-item tuples: [(name,), ...].
    Returns a dictionary keyed by professor name (use the id field for request_rmp_prof_details).

    """

    results = await asyncio.gather(
        *[rmp_prof_search(name) for (name,) in search_requests]
    )

    return {name: result for (name,), result in zip(search_requests, results)}

@mcp.tool()
async def request_rmp_prof_details(detail_requests: list[tuple[str]]) -> dict:
    """
    Search for specific professor details on RateMyProfessors.com by professor ID. Professor scores and details
    are important for students when choosing courses. You MUST call request_rmp_prof_search first to get professor IDs, 
    then use those IDs to call this function for details. Professor IDs are NOT the same as CRNs or term IDs, they are unique 
    identifiers for professors on RMP backend that are strings (not just numbers). Don't display the professor ID to users, it's only for internal use.

    This tool only returns a subset of all ratings. For more details, you can call request_rmp_prof_ratings_by_course to 
    get all rating for a specific professor for specific course codes.

    Accepts a list of one-item tuples: [(id,), ...].
    Returns a dictionary keyed by professor ID.

    """

    results = await asyncio.gather(
        *[rmp_prof_details(prof_id) for (prof_id,) in detail_requests]
    )

    return {prof_id: result for (prof_id,), result in zip(detail_requests, results)}


@mcp.tool()
async def request_rmp_prof_ratings_by_course(prof_id: str, course_codes: list[str]) -> dict:
    """
    Returns all professor ratings filtered by specific course codes from RMP. *** These course codes should be 
    the same as the ones returned by request_rmp_prof_details for each professor (differs for each professor). ***
    Keep in mind that a single course might have multiple course codes (e.g. COMP 1406 might be listed as COMP 1406, COMP 1406, 1406, etc.) 
    so make sure to include all relevant course codes for accurate filtering.
    
    The prof_id should only be obtained from request_rmp_prof_search, don't guess. 
    
    This tool is useful for a detailed view of a specific prof, don't use this if you are comparing a lot
    of profs (this returns all the ratings, can be quite a lot of info). If you are only comparing 3 or fewer profs for a specific course, 
    call this tool to get all ratings for each prof and then compare.

    """

    return await rmp_prof_ratings_by_course(prof_id, course_codes)


@mcp.tool()
async def request_subject_courses_text(course_subject: str) -> str:
    """
    Returns all courses for a specified subject (e.g. COMP). 
    This tool returns a large amount of text data, so only use this when necessary to not bloat context too much. 
    
    This includes course descriptions and requirement-related content present in that PDF.
    """

    return await fetch_subject_courses(course_subject)


@mcp.tool()
async def request_undergrad_programs() -> list[str]:
    """
    Returns all undergrad program slugs. Use these as arguments for request_undergrad_program_info
    to get detailed program info.

    Example slug: computerscience
    """

    return await fetch_undergrad_programs()


@mcp.tool()
async def request_undergrad_program_info(program_slug: str) -> str:
    """
    Returns all information about a specified undergrad program by slug (e.g. computerscience)
    
    This tool returns a large amount of text data, so only use this when necessary to not bloat context too much. 
    
    You MUST use request_undergrad_programs first to get valid program slugs. Don't guess what the slugs are.

    """

    return await fetch_undergrad_program_info(program_slug)
    

if __name__ == "__main__":
    mcp.run()