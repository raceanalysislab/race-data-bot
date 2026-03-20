import json
import os
import re
import glob
from typing import Dict, List, Optional, Tuple

SRC_GLOBS = [
    "data/extract/*.txt",
    "data/mbrace/*.txt",
]
OUT_DIR = "data/meet_perf"

ZEN2HAN = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "　": " ",
    "：": ":",
    "Ｒ": "R",
})

BLOCK_START_RE = re.compile(r"^(\d{2})BBGN$")
BLOCK_END_RE = re.compile(r"^(\d{2})BEND$")
DATE_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
DAYNO_RE = re.compile(r"第\s*(\d+)\s*日")
RACE_HEADER_RE = re.compile(r"^\s*([0-9]{1,2})R")
RACER_LINE_RE = re.compile(r"^\s*([1-6])\s*(\d{4})(.+)$")
GRADE_RE = re.compile(r"(A1|A2|B1|B2|L1|L2)")
VENUE_HEAD_RE = re.compile(r"^ボートレース\s*([^\s0-9]+)")


def norm(s: str) -> str:
    return str(s or "").translate(ZEN2HAN)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def read_text(path: str) -> str:
    for enc in ("utf-8", "cp932", "shift_jis", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def collect_source_files() -> List[str]:
    files: List[str] = []
    for pattern in SRC_GLOBS:
        files.extend(glob.glob(pattern))
    return sorted(set(files))


def extract_blocks(text: str) -> List[Tuple[str, List[str]]]:
    lines = text.splitlines()
    blocks: List[Tuple[str, List[str]]] = []

    current_jcd: Optional[str] = None
    current_lines: List[str] = []

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        m_start = BLOCK_START_RE.match(stripped)
        m_end = BLOCK_END_RE.match(stripped)

        if m_start:
            current_jcd = m_start.group(1)
            current_lines = []
            continue

        if m_end:
            end_jcd = m_end.group(1)
            if current_jcd == end_jcd:
                blocks.append((current_jcd, current_lines[:]))
            current_jcd = None
            current_lines = []
            continue

        if current_jcd:
            current_lines.append(line)

    return blocks


def extract_meta(lines: List[str], jcd: str) -> Dict:
    joined = "\n".join(norm(x) for x in lines[:30])

    venue = ""
    date_str = ""
    day_no = None

    for line in lines[:10]:
        s = norm(line).strip()
        m = VENUE_HEAD_RE.match(s)
        if m:
            venue = re.sub(r"\s+", "", m.group(1))
            break

    m_date = DATE_RE.search(joined)
    if m_date:
        y, m, d = m_date.groups()
        date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    m_day = DAYNO_RE.search(joined)
    if m_day:
        day_no = int(m_day.group(1))

    return {
        "jcd": jcd,
        "venue": venue,
        "date": date_str,
        "day_no": day_no,
    }


def find_perf_header_positions(lines: List[str]) -> Tuple[Optional[int], Optional[int]]:
    for line in lines:
        s = norm(line)
        if "今節成績" in s and "見" in s:
            perf_idx = s.find("今節成績")
            ken_idx = s.rfind("見")
            if perf_idx >= 0 and ken_idx > perf_idx:
                return perf_idx + len("今節成績"), ken_idx
    return None, None


def extract_name_from_tail(tail: str) -> str:
    s = norm(tail).strip()

    m_grade = GRADE_RE.search(s)
    if not m_grade:
        return ""

    left = s[:m_grade.start()]

    # 末尾の「年齢(1-2桁) + 支部 + 体重(2桁前後)」を落とす
    # 例: 村田敦55東京52
    m = re.match(r"^(.*?)(\d{1,2})([一-龥ぁ-んァ-ヶー]+)(\d{2})\s*$", left)
    if m:
        name = m.group(1)
        return re.sub(r"\s+", "", name)

    # 少し緩い保険
    m2 = re.match(r"^(.*?)(\d{1,2})([一-龥ぁ-んァ-ヶー]+)\s*$", left)
    if m2:
        name = m2.group(1)
        return re.sub(r"\s+", "", name)

    return ""


def extract_meet_perf_raw(line: str, perf_start: Optional[int], ken_start: Optional[int]) -> str:
    s = norm(line.rstrip("\n"))

    if perf_start is not None and ken_start is not None and len(s) >= perf_start:
        chunk = s[perf_start:ken_start].rstrip()
        if chunk:
            return chunk

    m = re.search(r"([FL転欠妨失エ0-9 ]+)\s+\d{0,2}\s*$", s)
    if m:
        return m.group(1).rstrip()

    return ""


def parse_racer_line(
    line: str,
    perf_start: Optional[int],
    ken_start: Optional[int],
) -> Optional[Dict]:
    s = norm(line)
    m = RACER_LINE_RE.match(s)
    if not m:
        return None

    boat_no = int(m.group(1))
    regno = m.group(2)
    tail = m.group(3)

    name = extract_name_from_tail(tail)
    meet_perf_raw = extract_meet_perf_raw(s, perf_start, ken_start)

    if not regno:
        return None

    return {
        "boat_no": boat_no,
        "regno": regno,
        "name": name,
        "meet_perf_raw": meet_perf_raw,
    }


def score_meet_perf(raw: str) -> Tuple[int, int]:
    s = str(raw or "")
    return (len(s.replace(" ", "")), len(s))


def parse_block(jcd: str, lines: List[str]) -> Dict:
    meta = extract_meta(lines, jcd)
    perf_start, ken_start = find_perf_header_positions(lines)

    racers: Dict[str, Dict] = {}
    current_race_no: Optional[int] = None

    for raw in lines:
        s = norm(raw)

        m_race = RACE_HEADER_RE.match(s)
        if m_race:
            current_race_no = int(m_race.group(1))
            continue

        racer = parse_racer_line(s, perf_start, ken_start)
        if not racer:
            continue

        regno = racer["regno"]
        prev = racers.get(regno)

        row = {
            "name": racer["name"],
            "meet_perf_raw": racer["meet_perf_raw"],
            "sample_race_no": current_race_no,
            "boat_no": racer["boat_no"],
        }

        if not prev:
            racers[regno] = row
            continue

        if score_meet_perf(row["meet_perf_raw"]) > score_meet_perf(prev.get("meet_perf_raw") or ""):
            racers[regno] = row

    return {
        "jcd": meta["jcd"],
        "venue": meta["venue"],
        "date": meta["date"],
        "day_no": meta["day_no"],
        "racers": racers,
    }


def write_json(data: Dict) -> Optional[str]:
    date_str = data.get("date") or ""
    jcd = data.get("jcd") or ""
    if not date_str or not jcd:
        return None

    ensure_dir(OUT_DIR)
    out_path = os.path.join(OUT_DIR, f"{date_str}_{jcd}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return out_path


def main() -> None:
    files = collect_source_files()
    if not files:
        print("no source files")
        return

    ensure_dir(OUT_DIR)

    written = 0
    parsed_blocks = 0

    for path in files:
        text = read_text(path)
        blocks = extract_blocks(text)

        for jcd, lines in blocks:
            data = parse_block(jcd, lines)
            out = write_json(data)
            if out:
                written += 1
            parsed_blocks += 1

    print(f"source_files: {len(files)}")
    print(f"parsed_blocks: {parsed_blocks}")
    print(f"written: {written}")


if __name__ == "__main__":
    main()