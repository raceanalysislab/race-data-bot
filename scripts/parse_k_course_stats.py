import os
import re
import json
from collections import defaultdict

EXTRACT_DIR = "data/extract_k"
OUT_PATH = "data/site/course_stats_3y.json"


def parse_line(line):
    """
    成績行を解析
    """
    m = re.match(
        r"\s*(\d{2})\s+(\d)\s+(\d{4})\s+(.+?)\s+\d+\s+\d+\s+\d+\.\d+\s+(\d)\s+([0-9\.F]+)",
        line
    )

    if not m:
        return None

    rank = m.group(1)
    lane = int(m.group(2))
    regno = m.group(3)
    course = int(m.group(5))
    st = m.group(6)

    try:
        st = float(st)
    except:
        st = None

    return rank, lane, regno, course, st


def parse_kimarite(line):
    """
    決まり手を取得
    """
    m = re.search(r"(逃げ|差し|まくり|まくり差し|抜き|恵まれ)", line)
    if m:
        return m.group(1)
    return None


def init_course():
    return {
        "starts": 0,
        "wins": 0,
        "place2": 0,
        "place3": 0,
        "st_sum": 0,
        "st_count": 0,
        "kimarite": defaultdict(int)
    }


stats = defaultdict(lambda: {i: init_course() for i in range(1, 7)})

files = sorted(os.listdir(EXTRACT_DIR))

for fn in files:
    if not fn.lower().endswith(".txt"):
        continue

    path = os.path.join(EXTRACT_DIR, fn)

    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    current_kimarite = None

    for line in lines:

        k = parse_kimarite(line)
        if k:
            current_kimarite = k
            continue

        parsed = parse_line(line)

        if not parsed:
            continue

        rank, lane, regno, course, st = parsed

        if rank.startswith("F") or rank.startswith("S"):
            continue

        course_stat = stats[regno][course]

        course_stat["starts"] += 1

        if st is not None:
            course_stat["st_sum"] += st
            course_stat["st_count"] += 1

        if rank == "01":
            course_stat["wins"] += 1

            if current_kimarite:
                course_stat["kimarite"][current_kimarite] += 1

        if rank in ("01", "02"):
            course_stat["place2"] += 1

        if rank in ("01", "02", "03"):
            course_stat["place3"] += 1


# 平均ST計算
for regno in stats:
    for course in stats[regno]:

        c = stats[regno][course]

        if c["st_count"] > 0:
            c["avg_st"] = round(c["st_sum"] / c["st_count"], 3)
        else:
            c["avg_st"] = None

        del c["st_sum"]
        del c["st_count"]
        c["kimarite"] = dict(c["kimarite"])


os.makedirs("data/site", exist_ok=True)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False)

print("generated:", OUT_PATH)
print("players:", len(stats))