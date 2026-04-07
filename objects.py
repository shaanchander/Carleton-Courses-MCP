class course:
    def __init__(self, subject: str, code: str, title: str, start_date: str = "", end_date: str = "", meeting_days: list[str] = [], meeting_times: list[str] = [], credits: int = 0, instructor: str = "Unknown", session_type: str = "", crn: int = 0, section: str = "", section_information: str = "", status: str = ""):
        self.crn = crn
        self.subject = subject
        self.code = code
        self.title = title
        self.start_date = start_date
        self.end_date = end_date
        self.meeting_days = meeting_days
        self.meeting_times = meeting_times
        self.credits = credits
        self.instructor = instructor
        self.session_type = session_type # lecture, lab, tutorial, etc.
        self.section = section # A, B, C, etc.
        self.section_information = section_information
        self.status = status # open, closed, waitlist, etc.

    def __str__(self):
        return str(self.__dict__)