from html import unescape
import re

from objects import course
import httpx

CARLETON_COURSE_SEARCH_URL = "https://central.carleton.ca/prod/bwysched.p_course_search"

async def course_search(course_subject: str, course_code: str = "") -> dict:
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
        ('term_code', '202620'),
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

    rows = re.findall(r"<tr\b[^>]*>.*?</tr>", raw_html, flags=re.S | re.I)
    for idx, row in enumerate(rows):
        if 'name="select_action"' not in row:
            continue

        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if len(cells) < 11:
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
        section = clean_text(cells[4])
        title = clean_text(cells[5])
        credits = parse_credits(clean_text(cells[6]))
        session_type = clean_text(cells[7])
        instructor = clean_text(cells[10]) or "Unknown"

        start_date = ""
        end_date = ""
        meeting_days = []
        meeting_times = []

        # Detail rows for this course appear after the main row until the next row with a checkbox.
        detail_idx = idx + 1
        while detail_idx < len(rows) and 'name="select_action"' not in rows[detail_idx]:
            detail_text = clean_text(rows[detail_idx])
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
            )
        )
    

    return {
        "results": courses
    }