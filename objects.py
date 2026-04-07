# TODO:
# - Add prerequisites, credits, instructor

class course:
    def __init__(self, subject: str, code: str, title: str):
        self.subject = subject
        self.code = code
        self.title = title
        # self.description = description

    def __str__(self):
        return f"{self.subject}{self.code}: {self.title}"