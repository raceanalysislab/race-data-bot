import json
import os
import re
import glob
from typing import Dict, List, Optional, Tuple

SRC_GLOB = "data/mbrace/*.txt"
OUT_DIR = "data/meet_perf"

ZEN2HAN = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "　": " ",
    "：": ":",
    "Ｒ": "R",
    "第": "第",
    "日": "日",
})

BLOCK_START_RE = re.compile(r"^(\d{2})BBGN$")
BLOCK_END_RE = re.compile(r"^(\d{2})BEND$")
DATE_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")
DAYNO_RE = re.compile(r"第\s*(\d+)\s*日")
RACE_HEADER_RE = re.compile(r"^\s*([0-9０-９]{1,2})Ｒ")
RACER_LINE_RE = re.compile(r"^\s*([1-6])\s*(\d{4})(.+)$")


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


def extract_blocks(text: str) -> List[Tuple[str, List[str]]]:
    lines = text.splitlines()
    blocks: List[Tuple[str, List[str]]] = []

    current_jcd: Optional[str] = None
    current_lines: List[str] = []

    for raw in lines:
        line = raw.rstrip("\n")
        m_start = BLOCK_START_RE.match(line.strip())
        m_end = BLOCK_END_RE.match(line.strip())

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
    joined = "\n".join(norm(x) for x in lines[:20])

    venue = ""
    date_str = ""
    day_no = None

    for line in lines[:8]:
        s = norm(line).strip()
        if s.startswith("ボートレース"):
            venue = s.replace("ボートレース", "", 1).strip()
            venue = re.sub(r"\s+", "", venue)
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


def clean_name(raw_tail: str) -> str:
    s = norm(raw_tail)
    m = re.match(r"([^\d ]+)", s.strip())
    if not m:
        return ""
    return re.sub(r"\s+", "", m.group(1))


def extract_meet_perf_raw(line: str, perf_start: Optional[int], ken_start: Optional[int]) -> str:
    s = norm(line.rstrip("\n"))

    if perf_start is not None and ken_start is not None and len(s) >= perf_start:
        chunk = s[perf_start:ken_start]
        chunk = chunk.rstrip()
        chunk = re.sub(r"\s+$", "", chunk)
        chunk = re.sub(r"[ ]{2,}", "  ", chunk)
        chunk = chunk.strip()
        if chunk:
            return chunk

    m = re.search(r"([FL転欠妨失エ0-9 ]+)\s+\d*\s*$", s)
    if m:
      return m.group(1).strip()

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

    name = clean_name(tail)
    meet_perf_raw = extract_meet_perf_raw(s, perf_start, ken_start)

    if not regno:
        return None

    return {
        "boat_no": boat_no,
        "regno": regno,
        "name": name,
        "meet_perf_raw": meet_perf_raw,
    }


def parse_block(jcd: str, lines: List[str]) -> Dict:
    meta = extract_meta(lines, jcd)
    perf_start, ken_start = find_perf_header_positions(lines)

    racers: Dict[str, Dict] = {}
    current_race_no: Optional[int] = None

    for raw in lines:
        s = norm(raw)

        m_race = RACE_HEADER_RE.match(s)
        if m_race:
            current_race_no = int(norm(m_race.group(1)))
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

        prev_raw = str(prev.get("meet_perf_raw") or "")
        new_raw = str(racer.get("meet_perf_raw") or "")

        if len(new_raw) > len(prev_raw):
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
    files = sorted(glob.glob(SRC_GLOB))
    if not files:
        print("no source files")
        return

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

    print(f"parsed_blocks: {parsed_blocks}")
    print(f"written: {written}")


if __name__ == "__main__":
    main()