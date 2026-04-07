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

    course_subject = course_subject.upper().strip()
    course_code = course_code.strip()

    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", raw_html, flags=re.S | re.I):
        if 'name="select_action"' not in row:
            continue

        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if len(cells) < 6:
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

        title = clean_text(cells[5])
        courses.append(course(subject, code, title))
    

    return {
        "results": courses
    }