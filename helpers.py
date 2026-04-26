from html import unescape
import re
import random
from io import BytesIO
from typing import Any

from objects import course
import httpx, asyncio
from pypdf import PdfReader

CARLETON_COURSE_SEARCH_URL = "https://central.carleton.ca/prod/bwysched.p_course_search"
RMP_GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"

async def course_search(course_subject: str, course_code: str = "", course_term: int = 202620) -> dict:
    """
    Search for courses based on subject and optional course code.
    
    Args:
        course_subject (str): The subject of the course (e.g., "COMP").
        course_code (str, optional): The specific course code (e.g., "1405"). Defaults to "".
    
    Returns:
        dict: A dictionary containing the search results.
    """

    courses = []
    session_id = str(random.randint(10000000, 99999999))

    # fetch raw html from Carleton course search page
    data = [
        ('wsea_code', 'EXT'),
        ('term_code', str(course_term)),
        ('session_id', session_id),
        ('ws_numb', ''),
        ('sel_aud', 'dummy'),
        ('sel_subj', 'dummy'),
        ('sel_camp', 'dummy'),
        ('sel_sess', 'dummy'),
        ('sel_attr', 'dummy'),
        ('sel_levl', 'dummy'),
        ('sel_schd', 'dummy'),
        ('sel_insm', 'dummy'),
        ('sel_link', 'dummy'),
        ('sel_wait', 'dummy'),
        ('sel_day', 'dummy'),
        ('sel_begin_hh', 'dummy'),
        ('sel_begin_mi', 'dummy'),
        ('sel_begin_am_pm', 'dummy'),
        ('sel_end_hh', 'dummy'),
        ('sel_end_mi', 'dummy'),
        ('sel_end_am_pm', 'dummy'),
        ('sel_instruct', 'dummy'),
        ('sel_special', 'dummy'),
        ('sel_resd', 'dummy'),
        ('sel_breadth', 'dummy'),
        ('sel_levl', 'UG'),
        ('sel_subj', course_subject),
        ('sel_number', course_code),
        ('sel_crn', ''),
        ('sel_special', 'N'),
        ('sel_sess', ''),
        ('sel_schd', ''),
        ('sel_instruct', ''),
        ('sel_begin_hh', '0'),
        ('sel_begin_mi', '0'),
        ('sel_begin_am_pm', 'a'),
        ('sel_end_hh', '0'),
        ('sel_end_mi', '0'),
        ('sel_end_am_pm', 'a'),
        ('sel_day', 'm'),
        ('sel_day', 't'),
        ('sel_day', 'w'),
        ('sel_day', 'r'),
        ('sel_day', 'f'),
        ('sel_day', 's'),
        ('sel_day', 'u'),
        ('block_button', ''),
    ]

    raw_html = None
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(CARLETON_COURSE_SEARCH_URL, params=data ,timeout=30.0)
            response.raise_for_status()
            raw_html = response.text
        except Exception:
            return None

    # parse html to extract course information and populate the courses list with course objects
    def clean_text(fragment: str) -> str:
        text = re.sub(r"<[^>]+>", "", fragment)
        return unescape(re.sub(r"\s+", " ", text)).strip()

    def parse_credits(raw_value: str):
        raw_value = raw_value.strip()
        if not raw_value:
            return 0
        try:
            value = float(raw_value)
            return int(value) if value.is_integer() else value
        except ValueError:
            return 0

    def parse_meeting_info(raw_text: str):
        start_date = ""
        end_date = ""
        meeting_days = []
        meeting_times = []
        section_information = ""

        date_match = re.search(r"Meeting Date:\s*(.*?)\s*to\s*(.*?)\s*(?:Days:|$)", raw_text, flags=re.I)
        if date_match:
            start_date = date_match.group(1).strip()
            end_date = date_match.group(2).strip()

        days_match = re.search(r"Days:\s*(.*?)\s*(?:Time:|$)", raw_text, flags=re.I)
        if days_match:
            days_text = days_match.group(1).strip()
            if days_text:
                meeting_days = days_text.split()

        time_match = re.search(r"Time:\s*(.*)$", raw_text, flags=re.I)
        if time_match:
            time_text = time_match.group(1).strip()
            if time_text:
                meeting_times = [time_text]

        return start_date, end_date, meeting_days, meeting_times

    course_subject = course_subject.upper().strip()
    course_code = course_code.strip()

    def is_course_row(cells: list[str]) -> bool:
        if len(cells) < 11:
            return False

        crn_text = clean_text(cells[2])
        subject_text = clean_text(cells[3])
        if not re.fullmatch(r"\d+", crn_text):
            return False
        if not re.match(r"^[A-Za-z]{3,5}\s+\S+", subject_text):
            return False
        return True

    rows = re.findall(r"<tr\b[^>]*>.*?</tr>", raw_html, flags=re.S | re.I)
    for idx, row in enumerate(rows):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if not is_course_row(cells):
            continue

        subject_text = clean_text(cells[3])
        subject_parts = subject_text.split(None, 1)
        if len(subject_parts) != 2:
            continue

        subject, code = subject_parts[0].upper(), subject_parts[1].strip()
        if subject != course_subject:
            continue
        if course_code and code != course_code:
            continue

        crn_text = clean_text(cells[2])
        status = clean_text(cells[1])
        section = clean_text(cells[4])
        title = clean_text(cells[5])
        credits = parse_credits(clean_text(cells[6]))
        session_type = clean_text(cells[7])
        instructor = clean_text(cells[10]) or "Unknown"

        start_date = ""
        end_date = ""
        meeting_days = []
        meeting_times = []

        # Detail rows for this course appear after the main row until the next main course row.
        detail_idx = idx + 1
        while detail_idx < len(rows):
            detail_row = rows[detail_idx]
            detail_cells = re.findall(r"<td\b[^>]*>(.*?)</td>", detail_row, flags=re.S | re.I)
            if is_course_row(detail_cells):
                break

            detail_text = clean_text(detail_row)
            if "Meeting Date:" in detail_text:
                parsed_start, parsed_end, parsed_days, parsed_times = parse_meeting_info(detail_text)
                if parsed_start:
                    start_date = parsed_start
                if parsed_end:
                    end_date = parsed_end
                if parsed_days:
                    meeting_days = parsed_days
                if parsed_times:
                    meeting_times = parsed_times

            section_info_match = re.search(r"Section Information:\s*(.*)$", detail_text, flags=re.I)
            if section_info_match:
                parsed_section_information = section_info_match.group(1).strip()
                if parsed_section_information:
                    section_information = parsed_section_information
            detail_idx += 1

        try:
            crn = int(crn_text)
        except ValueError:
            crn = 0

        courses.append(
            course(
                subject=subject,
                code=code,
                title=title,
                start_date=start_date,
                end_date=end_date,
                meeting_days=meeting_days,
                meeting_times=meeting_times,
                credits=credits,
                instructor=instructor,
                session_type=session_type,
                crn=crn,
                section=section,
                section_information=section_information,
                status=status,
            )
        )
    

    return {
        "results": courses
    }



async def search_terms() -> dict[str, str]:
    """Fetch available search terms as {term_id: friendly_name}."""
    url = "https://central.carleton.ca/prod/bwysched.p_select_term?wsea_code=EXT"
    
    terms: dict[str, str] = {}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            raw_html = response.text
        except Exception:
            return terms

    # Example option: <option value="202620">Summer 2026 (May-August)</option>
    term_matches = re.findall(
        r'<option\s+value="(\d{6})"[^>]*>(.*?)</option>',
        raw_html,
        flags=re.I | re.S,
    )
    for term_id, friendly_name in term_matches:
        text = re.sub(r"<[^>]+>", "", friendly_name)
        terms[int(term_id.strip())] = unescape(re.sub(r"\s+", " ", text)).strip()

    return terms

async def course_details(crn: int, term_id: int) -> dict:
    """Fetch detailed information for a specific course by CRN."""
    
    url = f"https://central.carleton.ca/prod/bwysched.p_display_course?wsea_code=EXT&term_code={term_id}&disp=0&crn={str(crn)}"

    details = {}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            raw_html = response.text
        except Exception:
            return details
    
    # Parse HTML for course details and normalize fields into a stable structure.
    def clean_text(fragment: str) -> str:
        text_with_breaks = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
        text_without_tags = re.sub(r"<[^>]+>", "", text_with_breaks)
        unescaped = unescape(text_without_tags)
        lines = [re.sub(r"\s+", " ", line).strip() for line in unescaped.splitlines()]
        return "\n".join([line for line in lines if line])

    def parse_numeric_value(value: str) -> int | float | str | None:
        stripped = value.strip()
        if not stripped:
            return ""
        if stripped == "{None}":
            return None
        if re.fullmatch(r"\d+", stripped):
            return int(stripped)
        if re.fullmatch(r"\d*\.\d+", stripped):
            parsed = float(stripped)
            return int(parsed) if parsed.is_integer() else parsed
        return stripped

    label_to_key = {
        "Registration Term": "registration_term",
        "CRN": "crn",
        "Subject": "subject_full",
        "Long Title": "long_title",
        "Title": "title",
        "Course Description": "course_description",
        "Course Credit Value": "course_credit_value",
        "Schedule Type": "schedule_type",
        "Full Session Info": "full_session_info",
        "Status": "status",
        "Section Information": "section_information",
        "Year in Program": "year_in_program",
        "Level Restriction": "level_restriction",
        "Degree Restriction": "degree_restriction",
        "Major Restriction": "major_restriction",
        "Program Restrictions": "program_restrictions",
        "Department Restriction": "department_restriction",
        "Faculty Restriction": "faculty_restriction",
    }

    row_pattern = re.compile(
        r"<tr\b[^>]*>\s*<td\b[^>]*>(.*?)</td>\s*<td\b[^>]*>(.*?)</td>\s*</tr>",
        flags=re.I | re.S,
    )

    previous_key = None
    for raw_label, raw_value in row_pattern.findall(raw_html):
        label = clean_text(raw_label).rstrip(":").strip()
        value = clean_text(raw_value)

        # Skip meeting header/data rows from the nested schedule table.
        if label in {"Meeting Date", "Days", "Time", "Schedule", "Instructor"}:
            continue

        if label:
            key = label_to_key.get(label, re.sub(r"\W+", "_", label.lower()).strip("_"))
            parsed_value = parse_numeric_value(value)

            if key == "program_restrictions":
                details[key] = [parsed_value] if parsed_value not in ("", None) else []
            else:
                details[key] = parsed_value
            previous_key = key
            continue

        # Continuation rows (most commonly for program restrictions).
        if previous_key and value:
            parsed_value = parse_numeric_value(value)
            if isinstance(details.get(previous_key), list):
                if parsed_value not in ("", None):
                    details[previous_key].append(parsed_value)
            elif details.get(previous_key) in ("", None):
                details[previous_key] = parsed_value

    subject_full = details.get("subject_full")
    if isinstance(subject_full, str) and subject_full:
        parts = subject_full.split()
        if len(parts) >= 2:
            details["subject"] = parts[0]
            details["code"] = parts[1]
        if len(parts) >= 3:
            details["section"] = parts[2]

    meetings: list[dict[str, Any]] = []
    meeting_table_match = re.search(
        r"<table\b[^>]*>\s*<tr>\s*<td><b>Meeting Date</b></td>\s*<td><b>Days</b></td>\s*<td><b>Time</b></td>\s*<td><b>Schedule</b></td>\s*<td><b>Instructor</b></td>\s*</tr>(.*?)</table>",
        raw_html,
        flags=re.I | re.S,
    )

    if meeting_table_match:
        meeting_rows_html = meeting_table_match.group(1)
        for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", meeting_rows_html, flags=re.I | re.S):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
            if len(cells) != 5:
                continue

            meeting_date = clean_text(cells[0])
            days_text = clean_text(cells[1])
            time_text = clean_text(cells[2])
            schedule = clean_text(cells[3])
            instructor = clean_text(cells[4])

            start_date = ""
            end_date = ""
            date_match = re.match(r"^(.*?)\s+to\s+(.*?)$", meeting_date)
            if date_match:
                start_date = date_match.group(1).strip()
                end_date = date_match.group(2).strip()

            meetings.append(
                {
                    "meeting_date": meeting_date,
                    "start_date": start_date,
                    "end_date": end_date,
                    "days": days_text.split() if days_text else [],
                    "time": time_text,
                    "schedule": schedule,
                    "instructor": instructor,
                }
            )

    details["meetings"] = meetings
    return details
    

async def rmp_prof_search(professor_name: str) -> list[dict]:
    """Search for professor ratings on RateMyProfessors.com by name."""
    
    profs = []
    response_json = None


    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0'
    }

    json_data = {
        'query': 'query NewSearchTeachersQuery(\n  $query: TeacherSearchQuery!\n  $count: Int\n  $includeCompare: Boolean!\n) {\n  newSearch {\n    teachers(query: $query, first: $count) {\n      didFallback\n      edges {\n        cursor\n        node {\n          id\n          legacyId\n          firstName\n          lastName\n          department\n          departmentId\n          school {\n            legacyId\n            name\n            id\n          }\n          ...CompareProfessorsColumn_teacher @include(if: $includeCompare)\n        }\n      }\n    }\n  }\n}\n\nfragment CompareProfessorsColumn_teacher on Teacher {\n  id\n  legacyId\n  firstName\n  lastName\n  school {\n    legacyId\n    name\n    id\n  }\n  department\n  departmentId\n  avgRating\n  avgDifficulty\n  numRatings\n  wouldTakeAgainPercentRounded\n  mandatoryAttendance {\n    yes\n    no\n    neither\n    total\n  }\n  takenForCredit {\n    yes\n    no\n    neither\n    total\n  }\n  ...NoRatingsArea_teacher\n  ...RatingDistributionWrapper_teacher\n}\n\nfragment NoRatingsArea_teacher on Teacher {\n  lastName\n  ...RateTeacherLink_teacher\n}\n\nfragment RateTeacherLink_teacher on Teacher {\n  legacyId\n  numRatings\n  lockStatus\n}\n\nfragment RatingDistributionChart_ratingsDistribution on ratingsDistribution {\n  r1\n  r2\n  r3\n  r4\n  r5\n}\n\nfragment RatingDistributionWrapper_teacher on Teacher {\n  ...NoRatingsArea_teacher\n  ratingsDistribution {\n    total\n    ...RatingDistributionChart_ratingsDistribution\n  }\n}\n',
        'operationName': 'NewSearchTeachersQuery',
        'variables': {
            'query': {
                'text': professor_name,
                'schoolID': 'U2Nob29sLTE0MjA=',
            },
            'count': 6,
            'includeCompare': False,
        },
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(RMP_GRAPHQL_URL, headers=headers, json=json_data, timeout=30.0)
            response.raise_for_status()
            response_json = response.json()
        except Exception as exc:
            print(f"rmp_prof_search request failed: {exc}")
            return profs

    edges = (
        response_json.get("data", {})
        .get("newSearch", {})
        .get("teachers", {})
        .get("edges", [])
    )

    for edge in edges:
        node = edge.get("node", {})
        if node:
            profs.append(node)

    return profs
    

async def rmp_prof_details(professor_id: str) -> dict:
    """Fetch detailed professor information from RateMyProfessors.com by professor ID."""
    
    details = {}
    response_json = None

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0'
    }

    json_data = {
        'query': 'query TeacherRatingsPageQuery(\n  $id: ID!\n) {\n  node(id: $id) {\n    __typename\n    ... on Teacher {\n      id\n      legacyId\n      firstName\n      lastName\n      department\n      school {\n        legacyId\n        name\n        city\n        state\n        country\n        id\n      }\n      lockStatus\n      ...StickyHeaderContent_teacher\n      ...MiniStickyHeader_teacher\n      ...TeacherBookmark_teacher\n      ...RatingDistributionWrapper_teacher\n      ...TeacherInfo_teacher\n      ...SimilarProfessors_teacher\n      ...TeacherRatingTabs_teacher\n    }\n    id\n  }\n}\n\nfragment CompareProfessorLink_teacher on Teacher {\n  legacyId\n}\n\nfragment CourseMeta_rating on Rating {\n  attendanceMandatory\n  wouldTakeAgain\n  grade\n  textbookUse\n  isForOnlineClass\n  isForCredit\n}\n\nfragment HeaderDescription_teacher on Teacher {\n  id\n  legacyId\n  firstName\n  lastName\n  department\n  school {\n    legacyId\n    name\n    city\n    state\n    id\n  }\n  ...TeacherTitles_teacher\n  ...TeacherBookmark_teacher\n  ...RateTeacherLink_teacher\n  ...CompareProfessorLink_teacher\n}\n\nfragment HeaderRateButton_teacher on Teacher {\n  ...RateTeacherLink_teacher\n  ...CompareProfessorLink_teacher\n}\n\nfragment MiniStickyHeader_teacher on Teacher {\n  id\n  legacyId\n  firstName\n  lastName\n  department\n  departmentId\n  school {\n    legacyId\n    name\n    city\n    state\n    id\n  }\n  ...TeacherBookmark_teacher\n  ...RateTeacherLink_teacher\n  ...CompareProfessorLink_teacher\n}\n\nfragment NameLink_teacher on Teacher {\n  isProfCurrentUser\n  id\n  legacyId\n  firstName\n  lastName\n  school {\n    name\n    id\n  }\n}\n\nfragment NameTitle_teacher on Teacher {\n  id\n  firstName\n  lastName\n  department\n  school {\n    legacyId\n    name\n    id\n  }\n  ...TeacherDepartment_teacher\n  ...TeacherBookmark_teacher\n}\n\nfragment NoRatingsArea_teacher on Teacher {\n  lastName\n  ...RateTeacherLink_teacher\n}\n\nfragment NumRatingsLink_teacher on Teacher {\n  numRatings\n  ...RateTeacherLink_teacher\n}\n\nfragment ProfessorNoteEditor_rating on Rating {\n  id\n  legacyId\n  class\n  teacherNote {\n    id\n    teacherId\n    comment\n  }\n}\n\nfragment ProfessorNoteEditor_teacher on Teacher {\n  id\n}\n\nfragment ProfessorNoteFooter_note on TeacherNotes {\n  legacyId\n  flagStatus\n}\n\nfragment ProfessorNoteFooter_teacher on Teacher {\n  legacyId\n  isProfCurrentUser\n}\n\nfragment ProfessorNoteHeader_note on TeacherNotes {\n  createdAt\n  updatedAt\n}\n\nfragment ProfessorNoteHeader_teacher on Teacher {\n  lastName\n}\n\nfragment ProfessorNoteSection_rating on Rating {\n  teacherNote {\n    ...ProfessorNote_note\n    id\n  }\n  ...ProfessorNoteEditor_rating\n}\n\nfragment ProfessorNoteSection_teacher on Teacher {\n  ...ProfessorNote_teacher\n  ...ProfessorNoteEditor_teacher\n}\n\nfragment ProfessorNote_note on TeacherNotes {\n  comment\n  ...ProfessorNoteHeader_note\n  ...ProfessorNoteFooter_note\n}\n\nfragment ProfessorNote_teacher on Teacher {\n  ...ProfessorNoteHeader_teacher\n  ...ProfessorNoteFooter_teacher\n}\n\nfragment RateTeacherLink_teacher on Teacher {\n  legacyId\n  numRatings\n  lockStatus\n}\n\nfragment RatingDistributionChart_ratingsDistribution on ratingsDistribution {\n  r1\n  r2\n  r3\n  r4\n  r5\n}\n\nfragment RatingDistributionWrapper_teacher on Teacher {\n  ...NoRatingsArea_teacher\n  ratingsDistribution {\n    total\n    ...RatingDistributionChart_ratingsDistribution\n  }\n}\n\nfragment RatingFooter_rating on Rating {\n  id\n  comment\n  adminReviewedAt\n  flagStatus\n  legacyId\n  thumbsUpTotal\n  thumbsDownTotal\n  thumbs {\n    thumbsUp\n    thumbsDown\n    computerId\n    id\n  }\n  teacherNote {\n    id\n  }\n  ...Thumbs_rating\n}\n\nfragment RatingFooter_teacher on Teacher {\n  id\n  legacyId\n  lockStatus\n  isProfCurrentUser\n  ...Thumbs_teacher\n}\n\nfragment RatingHeader_rating on Rating {\n  legacyId\n  date\n  class\n  helpfulRating\n  clarityRating\n  isForOnlineClass\n}\n\nfragment RatingSuperHeader_rating on Rating {\n  legacyId\n}\n\nfragment RatingSuperHeader_teacher on Teacher {\n  firstName\n  lastName\n  legacyId\n  school {\n    name\n    id\n  }\n}\n\nfragment RatingTags_rating on Rating {\n  ratingTags\n}\n\nfragment RatingValue_teacher on Teacher {\n  avgRating\n  numRatings\n  ...NumRatingsLink_teacher\n}\n\nfragment RatingValues_rating on Rating {\n  helpfulRating\n  clarityRating\n  difficultyRating\n}\n\nfragment Rating_rating on Rating {\n  comment\n  flagStatus\n  createdByUser\n  teacherNote {\n    id\n  }\n  ...RatingHeader_rating\n  ...RatingSuperHeader_rating\n  ...RatingValues_rating\n  ...CourseMeta_rating\n  ...RatingTags_rating\n  ...RatingFooter_rating\n  ...ProfessorNoteSection_rating\n}\n\nfragment Rating_teacher on Teacher {\n  ...RatingFooter_teacher\n  ...RatingSuperHeader_teacher\n  ...ProfessorNoteSection_teacher\n}\n\nfragment RatingsFilter_teacher on Teacher {\n  courseCodes {\n    courseCount\n    courseName\n  }\n}\n\nfragment RatingsList_teacher on Teacher {\n  id\n  legacyId\n  lastName\n  numRatings\n  school {\n    id\n    legacyId\n    name\n    city\n    state\n    avgRating\n    numRatings\n  }\n  ...Rating_teacher\n  ...NoRatingsArea_teacher\n  ratings(first: 5) {\n    edges {\n      cursor\n      node {\n        ...Rating_rating\n        id\n        __typename\n      }\n    }\n    pageInfo {\n      hasNextPage\n      endCursor\n    }\n  }\n}\n\nfragment SimilarProfessorListItem_teacher on RelatedTeacher {\n  legacyId\n  firstName\n  lastName\n  avgRating\n}\n\nfragment SimilarProfessors_teacher on Teacher {\n  department\n  relatedTeachers {\n    legacyId\n    ...SimilarProfessorListItem_teacher\n    id\n  }\n}\n\nfragment StickyHeaderContent_teacher on Teacher {\n  ...HeaderDescription_teacher\n  ...HeaderRateButton_teacher\n  ...MiniStickyHeader_teacher\n}\n\nfragment TeacherBookmark_teacher on Teacher {\n  id\n  isSaved\n}\n\nfragment TeacherDepartment_teacher on Teacher {\n  department\n  departmentId\n  school {\n    legacyId\n    name\n    isVisible\n    id\n  }\n}\n\nfragment TeacherFeedback_teacher on Teacher {\n  numRatings\n  avgDifficulty\n  wouldTakeAgainPercent\n}\n\nfragment TeacherInfo_teacher on Teacher {\n  id\n  lastName\n  numRatings\n  ...RatingValue_teacher\n  ...NameTitle_teacher\n  ...TeacherTags_teacher\n  ...NameLink_teacher\n  ...TeacherFeedback_teacher\n  ...RateTeacherLink_teacher\n  ...CompareProfessorLink_teacher\n}\n\nfragment TeacherRatingTabs_teacher on Teacher {\n  numRatings\n  courseCodes {\n    courseName\n    courseCount\n  }\n  ...RatingsList_teacher\n  ...RatingsFilter_teacher\n}\n\nfragment TeacherTags_teacher on Teacher {\n  lastName\n  teacherRatingTags {\n    legacyId\n    tagCount\n    tagName\n    id\n  }\n}\n\nfragment TeacherTitles_teacher on Teacher {\n  department\n  school {\n    legacyId\n    name\n    id\n  }\n}\n\nfragment Thumbs_rating on Rating {\n  id\n  comment\n  adminReviewedAt\n  flagStatus\n  legacyId\n  thumbsUpTotal\n  thumbsDownTotal\n  thumbs {\n    computerId\n    thumbsUp\n    thumbsDown\n    id\n  }\n  teacherNote {\n    id\n  }\n}\n\nfragment Thumbs_teacher on Teacher {\n  id\n  legacyId\n  lockStatus\n  isProfCurrentUser\n}\n',
        'operationName': 'TeacherRatingsPageQuery',
        'variables': {
            'id': professor_id,
        },
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(RMP_GRAPHQL_URL, headers=headers, json=json_data, timeout=30.0)
            response.raise_for_status()
            response_json = response.json()
        except Exception as exc:
            print(f"rmp_prof_search request failed: {exc}")
            return details

    node = response_json.get("data", {}).get("node", {})
    if not isinstance(node, dict):
        return details

    dropped_keys = {
        "__typename",
        "school",
        "relatedTeachers",
        "pageInfo",
        "cursor",
        "departmentId",
        "isProfCurrentUser",
        "isSaved",
        "lockStatus",
        "thumbs",
    }

    def prune(value: Any):
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}

            for key, val in value.items():
                lower_key = key.lower()
                if key in dropped_keys or lower_key == "id" or lower_key.endswith("id"):
                    continue

                if key == "ratings" and isinstance(val, dict):
                    edges = val.get("edges", [])
                    ratings_list = []
                    for edge in edges:
                        if not isinstance(edge, dict):
                            continue
                        rating_node = edge.get("node", {})
                        pruned_rating = prune(rating_node)
                        if pruned_rating not in (None, "", [], {}):
                            ratings_list.append(pruned_rating)
                    cleaned["ratings"] = ratings_list
                    continue

                if key == "teacherRatingTags" and isinstance(val, list):
                    tags: dict[str, int] = {}
                    for tag in val:
                        if not isinstance(tag, dict):
                            continue
                        tag_name = tag.get("tagName")
                        tag_count = tag.get("tagCount")
                        if isinstance(tag_name, str) and tag_name.strip() and isinstance(tag_count, int):
                            tags[tag_name.strip()] = tag_count
                    cleaned["teacherRatingTags"] = tags
                    continue

                pruned_val = prune(val)
                if pruned_val in (None, "", [], {}):
                    continue
                cleaned[key] = pruned_val

            return cleaned

        if isinstance(value, list):
            cleaned_list = [prune(item) for item in value]
            return [item for item in cleaned_list if item not in (None, "", [], {})]

        return value

    details = prune(node)

    return details


async def rmp_prof_ratings_by_course(professor_id: str, course_codes: list[str]) -> dict:
    """Fetch professor ratings filtered by specific courses from RateMyProfessors.com."""
    
    ratings = {code: [] for code in course_codes}
    response_json = None

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0'
    }

    # query RMP graphql for each course code
    async with httpx.AsyncClient() as client:

        tasks = []

        for code in course_codes:

            json_data = {
                'query': 'query RatingsListQuery(\n  $count: Int!\n  $id: ID!\n  $courseFilter: String\n  $cursor: String\n) {\n  node(id: $id) {\n    __typename\n    ... on Teacher {\n      ...RatingsList_teacher_4pguUW\n    }\n    id\n  }\n}\n\nfragment CourseMeta_rating on Rating {\n  attendanceMandatory\n  wouldTakeAgain\n  grade\n  textbookUse\n  isForOnlineClass\n  isForCredit\n}\n\nfragment NoRatingsArea_teacher on Teacher {\n  lastName\n  ...RateTeacherLink_teacher\n}\n\nfragment ProfessorNoteEditor_rating on Rating {\n  id\n  legacyId\n  class\n  teacherNote {\n    id\n    teacherId\n    comment\n  }\n}\n\nfragment ProfessorNoteEditor_teacher on Teacher {\n  id\n}\n\nfragment ProfessorNoteFooter_note on TeacherNotes {\n  legacyId\n  flagStatus\n}\n\nfragment ProfessorNoteFooter_teacher on Teacher {\n  legacyId\n  isProfCurrentUser\n}\n\nfragment ProfessorNoteHeader_note on TeacherNotes {\n  createdAt\n  updatedAt\n}\n\nfragment ProfessorNoteHeader_teacher on Teacher {\n  lastName\n}\n\nfragment ProfessorNoteSection_rating on Rating {\n  teacherNote {\n    ...ProfessorNote_note\n    id\n  }\n  ...ProfessorNoteEditor_rating\n}\n\nfragment ProfessorNoteSection_teacher on Teacher {\n  ...ProfessorNote_teacher\n  ...ProfessorNoteEditor_teacher\n}\n\nfragment ProfessorNote_note on TeacherNotes {\n  comment\n  ...ProfessorNoteHeader_note\n  ...ProfessorNoteFooter_note\n}\n\nfragment ProfessorNote_teacher on Teacher {\n  ...ProfessorNoteHeader_teacher\n  ...ProfessorNoteFooter_teacher\n}\n\nfragment RateTeacherLink_teacher on Teacher {\n  legacyId\n  numRatings\n  lockStatus\n}\n\nfragment RatingFooter_rating on Rating {\n  id\n  comment\n  adminReviewedAt\n  flagStatus\n  legacyId\n  thumbsUpTotal\n  thumbsDownTotal\n  thumbs {\n    thumbsUp\n    thumbsDown\n    computerId\n    id\n  }\n  teacherNote {\n    id\n  }\n  ...Thumbs_rating\n}\n\nfragment RatingFooter_teacher on Teacher {\n  id\n  legacyId\n  lockStatus\n  isProfCurrentUser\n  ...Thumbs_teacher\n}\n\nfragment RatingHeader_rating on Rating {\n  legacyId\n  date\n  class\n  helpfulRating\n  clarityRating\n  isForOnlineClass\n}\n\nfragment RatingSuperHeader_rating on Rating {\n  legacyId\n}\n\nfragment RatingSuperHeader_teacher on Teacher {\n  firstName\n  lastName\n  legacyId\n  school {\n    name\n    id\n  }\n}\n\nfragment RatingTags_rating on Rating {\n  ratingTags\n}\n\nfragment RatingValues_rating on Rating {\n  helpfulRating\n  clarityRating\n  difficultyRating\n}\n\nfragment Rating_rating on Rating {\n  comment\n  flagStatus\n  createdByUser\n  teacherNote {\n    id\n  }\n  ...RatingHeader_rating\n  ...RatingSuperHeader_rating\n  ...RatingValues_rating\n  ...CourseMeta_rating\n  ...RatingTags_rating\n  ...RatingFooter_rating\n  ...ProfessorNoteSection_rating\n}\n\nfragment Rating_teacher on Teacher {\n  ...RatingFooter_teacher\n  ...RatingSuperHeader_teacher\n  ...ProfessorNoteSection_teacher\n}\n\nfragment RatingsList_teacher_4pguUW on Teacher {\n  id\n  legacyId\n  lastName\n  numRatings\n  school {\n    id\n    legacyId\n    name\n    city\n    state\n    avgRating\n    numRatings\n  }\n  ...Rating_teacher\n  ...NoRatingsArea_teacher\n  ratings(first: $count, after: $cursor, courseFilter: $courseFilter) {\n    edges {\n      cursor\n      node {\n        ...Rating_rating\n        id\n        __typename\n      }\n    }\n    pageInfo {\n      hasNextPage\n      endCursor\n    }\n  }\n}\n\nfragment Thumbs_rating on Rating {\n  id\n  comment\n  adminReviewedAt\n  flagStatus\n  legacyId\n  thumbsUpTotal\n  thumbsDownTotal\n  thumbs {\n    computerId\n    thumbsUp\n    thumbsDown\n    id\n  }\n  teacherNote {\n    id\n  }\n}\n\nfragment Thumbs_teacher on Teacher {\n  id\n  legacyId\n  lockStatus\n  isProfCurrentUser\n}\n',
                'operationName': 'RatingsListQuery',
                'variables': {
                    'count': 5,
                    'id': professor_id,
                    'courseFilter': None, # temp, replaced with each code in the loop
                    'cursor': None,
                },
            }

            json_data["variables"]["courseFilter"] = code
            tasks.append(client.post(RMP_GRAPHQL_URL, headers=headers, json=json_data, timeout=30.0))

        responses = await asyncio.gather(*tasks)

        # return responses[2].json()

        # process the results

        for response in responses:
            try:
                response.raise_for_status()
                response_json = response.json()

                edges = (
                    response_json.get("data", {})
                    .get("node", {})
                    .get("ratings", {})
                    .get("edges", [])
                )

                for edge in edges:
                    node = edge.get("node", {})
                    if node:
                        ratings[node["class"]].append(node)

            except Exception as exc:
                print(f"rmp_prof_search request failed: {exc}")
                return ratings

    return ratings

async def fetch_subject_courses(course_subject: str) -> str:
    """ Fetch full details of all courses for a given subject """

    subject = course_subject.strip().lower()
    if not subject:
        return ""

    url = f"https://calendar.carleton.ca/undergrad/courses/{course_subject}/{course_subject}.pdf"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
        except Exception:
            return ""

    try:
        # Parse PDF directly from response bytes without writing to disk.
        reader = PdfReader(BytesIO(response.content))
    except Exception:
        return ""

    pages: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        text = extracted.strip()
        if text:
            pages.append(text)

    return "\n\n".join(pages)