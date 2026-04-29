import json

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
from mcp.types import TextContent

mcp = FastMCP("Carleton Courses MCP")

REGISTRATION_TERMINOLOGY = {
    "understanding_registration_terms": {
        "Billing Hours": "The credit value used in fee calculation.",
        "Credit Hours": "The credit value of the course (ex: 0.5 or 1.0)",
        "CRN": "Course reference number (CRN) is the unique number that identifies a course. The CRN will vary depending on the section and on the term the course is offered. Each course component (i.e. lecture, tutorial, lab, etc.) will have its own CRN.",
        "Faculty": "A major teaching division of the University, divided into departments, schools or other units and headed by a Dean (e.g. Faculty of Arts and Social Sciences, Faculty of Science).",
        "Linked Courses": "Linked sections are sections that you must register in concurrently. If a section is identified as being linked, you must register in all parts of the course at the same time. Keep in mind that if you register for lecture section A, you must register in one of the associated linked sections (ex: discussion group) such as A1 or A2; you cannot add B1 or B2 to the section A lecture. See 'Tutorials and Discussion Groups' below for more information.",
        "Preclusion": "This is a term used to describe two or more courses that contain sufficient content in common that credit cannot be earned for more than one of the courses, but it does not mean that the courses are equivalent. For example, MATH 1007 precludes credit for MATH 1004. If you take MATH 1007 first, then register for 1004, you lose the credit gained for 1007.",
        "Prerequisite": "Sometimes courses require you to have a certain level of knowledge before registering. For example, you must take a first-year level course in Psychology before you can register in a second-year level Psychology course. Thus, the first-year course is said to be the prerequisite for the second-year course.",
        "Sections": "When you look at the class timetable, you will see that the same course, BUSI 1004 for instance, may be listed several times and identified as BUSI 1004 section A, section B and so forth. Each 'section' covers the same material in general but the instructors, times and even the textbook can be different. For this reason students must register in one section and stay in that section for the duration of the course.",
        "Tutorials and Discussion Groups": "Tutorials and discussion groups are required components that are linked to a lecture. They break larger courses into smaller groups of students in order to review material from the lectures, complete practice problems, or discuss readings related to the course. They are generally led by Teaching Assistants, and you are expected to attend.",
        "Waitlist": "A registration waitlist is a queue of students who are waiting for a space to open in a filled section of a course. Visit the Waitlisting page for more information.",
        "Year in Program": "Your year standing (your year level in your current program) may be different than the number of years you have been studying at Carleton. Year standing (e.g. First-year Undergraduate) is calculated according to the number of credits completed with passing grades and counting towards the degree. See section 3.1.8 of the Undergraduate Calendar for more information.",
    },
    "registration_and_error_codes": {
        "Open": "There are currently seats available in the course",
        "Full": "There are no seats available in the course",
        "Already Registered": "You are already registered in this section",
        "Already Waitlisted": "You are already on the waitlist for this section",
        "On Your Worksheet": "You have already added this hypothetical course to your worksheet, but you are not yet registered in it",
        "Cancelled": "The course has been cancelled for the selected term",
        "Waitlist Open": "There are no seats available in the course, but the course does have a waitlist enabled, and there are spaces available on the waitlist",
        "Waitlist Full": "There are no seats available in the course. The course has a waitlist enabled, but there are no spaces available on the waitlist",
        "Registration Closed": "The last day for registration into this class has passed; you can no longer register for this course.",
    },
    "other_registration_key_terms": {
        "First Year Seminar": "The First-Year Seminar is a prominent part of Carleton University's course offerings for incoming students to the Bachelor of Arts, Bachelor of Cognitive Science, Bachelor of Global and International Studies, Bachelor of Communication and Media Studies and Bachelor of Economics. Students are strongly encouraged to check regulations pertaining to first-year seminar registration on the First-year Seminar site. If you are taking a First Year Seminar (FYSM), please note that you can only register in, and receive credit for, one FYSM. The FYSM can either be in your major, or in a discipline that is of interest to you. University seminar courses are small classes designed to give students the opportunity to discuss and research topics of interest in a core subject area. Most university students are in their third or fourth year of study before they have the opportunity to take seminar courses. As a Carleton B.A., B.Cog.Sc., B.GInS., B.CoMS or B.Econ. student, you are provided with this experience at the first-year level through enrolment in your first-year seminar (FYSM). More information, and a list of First-year Seminar courses and topics, can be found on the First-year Seminar site. You can also view a short video explaining why you should take a First Year Seminar.",
        "Full Session Courses (Fall/Winter Courses)": "These classes are 1.0 credit, and they start in September and run until April. Instead of having a final exam in December, you will have a midterm, and then resume the class in January. To add a full session course, register in the fall portion of the course. The winter portion will automatically be added to your winter term registration. You must be in the same section for both terms. To drop a full session course, drop the Fall term portion of the course within the fall term deadlines. The winter portion will automatically be removed from your winter term registration. You can still drop the winter term portion only within the winter term deadlines.",
        "Linked Components (groups, labs, tutorials, etc.)": "Some courses may have a discussion group, tutorial or lab. These groups, tutorials and labs are known as LINKED components. Example: BUSI 1004 A (LEC) + BUSI 1004 A1 (TUT). To register in these courses you must add both sections to your schedule. If you do not register in all the required linked components for your course, you will receive a LINK ERROR and must try again. You can change sections of a tutorial or lab without having to drop your lecture at the same time. When changing your tutorial or lab section, you must select a replacement section from the same course letter section (i.e. changing from A1 to A3). Please note: This registration feature is only available for single term courses. For two-term courses, you risk losing your course registration when changing tutorial or lab sections. Watch our How To Video to learn how to change your lab/group/tutorial. Note: For full session linked courses you must add both sections to your schedule simultaneously.",
    },
}


@mcp.resource(
    "carleton://registration-terminology",
    name="registration_terminology",
    title="Carleton Registration Terminology",
    description="Carleton registration terminology definitions)",
    mime_type="application/json",
)
def registration_terminology_resource() -> str:
    """This resource provides definitions for key terms related to course registration at Carleton University.
    If you are ever unsure about what a term means when discussing course registration, refer to this resource for clarification.
    This resource is static and does not need to be called more than once per session.
    When discussing registration with a user, you should ***ALWAYS*** call this resource to ensure you provide the user with accurate information and definitions for any terms you see. """
    return json.dumps(REGISTRATION_TERMINOLOGY, indent=2, ensure_ascii=False)


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