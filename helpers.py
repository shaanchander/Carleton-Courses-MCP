from html import unescape
import re
from typing import Any

from objects import course
import httpx

CARLETON_COURSE_SEARCH_URL = "https://central.carleton.ca/prod/bwysched.p_course_search"

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

    # fetch raw html from Carleton course search page
    data = [
        ('wsea_code', 'EXT'),
        ('term_code', str(course_term)),
        ('session_id', '25259018'),
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
    
