"""Retain asserted clauses; uncertainty about a fact is not a positive claim."""
import re
from harness.textnorm import fold

UNKNOWN = re.compile(r'\b(chua co thong tin|chua (the )?(xac nhan|xac minh)|khong (the )?(xac nhan|biet)|chua ro|khong ro)\b')


def asserted_text(sentence):
    clauses = re.split(r'(?<!\d),|,(?!\d)|;|\bnhưng\b|\bnhung\b', sentence, flags=re.I)
    out = []
    for i, clause in enumerate(clauses):
        f = fold(clause).strip()
        if UNKNOWN.search(f):
            continue
        # A topic followed by "I have no information" is not an assertion of that topic.
        if re.match(r'^(ve( viec)?|doi voi|chuyen)\b', f) and i + 1 < len(clauses) and UNKNOWN.search(fold(clauses[i + 1])):
            continue
        out.append(clause)
    return ', '.join(out)


def curative_problems(text):
    problems = []
    for clause in re.split(r'[.!?;,]|\bnhưng\b', text, flags=re.I):
        f = fold(asserted_text(clause))
        if not re.search(r'\b(chua|dieu tri|tri)\s+(duoc\s+)?(benh|hen|tac tia|viem)|\btang tiet sua\b', f):
            continue
        raw = re.sub(r'\bkhông (những|chỉ)\b', '', clause.lower())
        raw = re.sub(r'\bkhong (nhung|chi)\b', '', raw)
        negative = (re.search(r'\b(không|chưa|chẳng)\b.{0,65}\b(chữa|trị|điều trị|tăng tiết sữa)\b', raw)
                    or re.search(r'\b(khong|chang)\b.{0,65}\b(chua|tri|dieu tri|tang tiet sua)\b', raw))
        if negative:
            continue
        problems.append('không được khẳng định công dụng điều trị/y tế chưa có nguồn; chuyển chuyên viên và không xác nhận công dụng')
    return problems
