"""Only execute unambiguous teacher notes; preserve other clauses for review."""
import re


_MULTIPLE = re.compile(r'(?:允许同组安排多名|同组可以安排多名|同组可安排多名|允许同组多名)(?:该教师负责的学生|其负责的学生|指导学生|学生)?')


def teacher_remark_rules(text):
    clauses = [part.strip() for part in re.split(r'[；;。\n]+', text or '') if part.strip()]
    recognized = [clause for clause in clauses if _MULTIPLE.fullmatch(clause)]
    return bool(recognized), [clause for clause in clauses if clause not in recognized]
