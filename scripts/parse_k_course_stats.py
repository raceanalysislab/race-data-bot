import os
import re
import json
from collections import defaultdict

EXTRACT_DIR = "data/extract_k"
OUT_PATH = "data/site/course_stats_3y.json"


def init_course():
    return {
        "starts": 0,
        "wins": 0,
        "place2": 0,
        "place3": 0,
        "st_sum": 0.0,
        "st_count": 0,
        "avg_st": None,
        "kimarite": defaultdict(int),
    }


stats = defaultdict(lambda: {str(i): init_course() for i in range(1, 7)})


def parse_result_line(line: str):
    """
    例:
    01  1 5229 吉　川　　晴　人 55   29  6.64   1    0.11     1.47.8 逃げ
    F   2 4408 仁　科　　さやか 35   68  6.76   2   F0.01      .  .
    """
    line = line.rstrip("\n")
    if not line.strip():
        return None

    # 着順 / 艇番 / 登番 を先頭から取る
    m = re.match(r"^\s*(\S+)\s+(\d)\s+(\d{4})\s+", line)
    if not m:
        return None

    rank = m.group(1)          # 01 / 02 / F / S1 ...
    lane = m.group(2)          # 艇番
    regno = m.group(3)         # 登番

    # 進入は 展示タイムの後ろ、STの前
    # ... 6.64   1    0.11 ...
    m_course_st = re.search(r"\d\.\d{2}\s+(\d)\s+([FSL]?\d\.\d{2}|[FSL]\d\.\d{2}|0\.\d{2})", line)
    if not m_course_st:
        return None

    course = m_course_st.group(1)
    st_raw = m_course_st.group(2)

    # 決まり手は行末
    m_k = re.search(r"(逃げ|差し|まくり差し|まくり|抜き|恵まれ)\s*$", line)
    kimarite = m_k.group(1) if m_k else None

    st = None
    if re.fullmatch(r"0\.\d{2}", st_raw):
        st = float(st_raw)

    return {
        "rank": rank,
        "lane": lane,
        "regno": regno,
        "course": course,
        "st": st,
        "kimarite": kimarite,
    }


def is_numeric_rank(rank: str) -> bool:
    return bool(re.fullmatch(r"\d{2}", rank))


def finalize():
    for regno, course_map in stats.items():
        for course, c in course_map.items():
            if c["st_count"] > 0:
                c["avg_st"] = round(c["st_sum"] / c["st_count"], 3)
            else:
                c["avg_st"] = None

            del c["st_sum"]
            del c["st_count"]
            c["kimarite"] = dict(c["kimarite"])


def main():
    txt_files = sorted(
        fn for fn in os.listdir(EXTRACT_DIR)
        if fn.lower().endswith(".txt")
    )

    for fn in txt_files:
        path = os.path.join(EXTRACT_DIR, fn)

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                row = parse_result_line(line)
                if not row:
                    continue

                rank = row["rank"]
                regno = row["regno"]
                course = row["course"]
                st = row["st"]
                kimarite = row["kimarite"]

                # F / S / L などは出走数に入れない
                if not is_numeric_rank(rank):
                    continue

                c = stats[regno][course]
                c["starts"] += 1

                if st is not None:
                    c["st_sum"] += st
                    c["st_count"] += 1

                if rank == "01":
                    c["wins"] += 1
                    if kimarite:
                        c["kimarite"][kimarite] += 1

                if rank in ("01", "02"):
                    c["place2"] += 1

                if rank in ("01", "02", "03"):
                    c["place3"] += 1

    finalize()

    os.makedirs("data/site", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False)

    print("generated:", OUT_PATH)
    print("players:", len(stats))


if __name__ == "__main__":
    main()