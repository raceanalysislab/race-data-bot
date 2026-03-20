import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

RE_KBGN = re.compile(r"^(\d{2})KBGN$")
RE_KEND = re.compile(r"^(\d{2})KEND$")
RE_DATE = re.compile(r"(\d{4})/\s*(\d{1,2})/\s*(\d{1,2})")
RE_DATE_SHORT = re.compile(r"(\d{1,2})/(\d{1,2})")
RE_DAYNO = re.compile(r"第\s*([0-9]+)\s*日")
RE_RACE_HEADER = re.compile(r"^\s*(\d{1,2})R")
RE_DISTANCE = re.compile(r"H\s*\d{3,4}m")
RE_RESULT_ROW = re.compile(
    r"^\s*"
    r"(\d{2}|S\d|F|K0)\s+"            # 着
    r"([1-6])\s+"                      # 艇
    r"(\d{4})\s+"                      # 登番
    r"(.+?)\s+"                        # 選手名
    r"(\d{1,3})\s+"                    # モーター
    r"(\d{1,3})\s+"                    # ボート
    r"([0-9]+\.[0-9]{2})\s+"           # 展示
    r"([1-6])\s+"                      # 進入
    r"([0-9]+\.[0-9]{2})\s+"           # ST
    r"(.+?)\s*$"                       # レースタイム以降
)


def norm_space(s: str) -> str:
    s = str(s or "")
    s = s.replace("　", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_event_title(title: str) -> str:
    s = norm_space(title)
    s = s.replace("～", "〜").replace("~", "〜")
    s = re.sub(r"第\s*\d+\s*回", "", s)
    s = re.sub(r"\bSG\b", "", s)
    s = re.sub(r"\bG[123]\b", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def read_text_auto(path: str) -> List[str]:
    for enc in ("cp932", "utf-8-sig", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as f:
                return [x.rstrip("\n") for x in f]
        except Exception:
            continue

    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return [x.rstrip("\n") for x in f]


def glob_safe(pattern: str) -> List[str]:
    import glob
    return glob.glob(pattern)


def collect_k_txt_files() -> List[str]:
    patterns = [
        os.path.join("data", "extract", "k*.txt"),
        os.path.join("data", "extract_k", "k*.txt"),
        os.path.join("data", "k*.txt"),
    ]

    files: List[str] = []
    for pattern in patterns:
        files.extend(sorted([p for p in glob_safe(pattern) if os.path.isfile(p)]))

    return sorted(set(files))


def split_blocks(lines: List[str]) -> List[Tuple[str, List[str]]]:
    blocks: List[Tuple[str, List[str]]] = []
    cur_jcd: Optional[str] = None
    cur: List[str] = []

    for line in lines:
        stripped = line.strip()

        m_start = RE_KBGN.match(stripped)
        if m_start:
            if cur_jcd and cur:
                blocks.append((cur_jcd, cur))
            cur_jcd = m_start.group(1)
            cur = []
            continue

        m_end = RE_KEND.match(stripped)
        if m_end:
            end_jcd = m_end.group(1)
            if cur_jcd == end_jcd:
                blocks.append((cur_jcd, cur))
            cur_jcd = None
            cur = []
            continue

        if cur_jcd:
            cur.append(line)

    if cur_jcd and cur:
        blocks.append((cur_jcd, cur))

    return blocks


def parse_venue(block: List[str]) -> str:
    for line in block[:8]:
        s = norm_space(line)
        if "［成績］" in s:
            return s.split("［成績］", 1)[0].replace(" ", "")
    return ""


def parse_date(block: List[str]) -> str:
    year_now = datetime.now(JST).year

    for line in block[:30]:
        s = norm_space(line)
        m = RE_DATE.search(s)
        if m:
            y, mm, dd = m.groups()
            return f"{int(y):04d}-{int(mm):02d}-{int(dd):02d}"

    for line in block[:20]:
        s = norm_space(line)
        m = RE_DATE_SHORT.search(s)
        if m:
            mm, dd = m.groups()
            return f"{year_now:04d}-{int(mm):02d}-{int(dd):02d}"

    return ""


def parse_day_no(block: List[str]) -> Optional[int]:
    joined = "\n".join(norm_space(x) for x in block[:30])
    m = RE_DAYNO.search(joined)
    if not m:
        return None

    try:
        return int(m.group(1))
    except Exception:
        return None


def parse_event_title(block: List[str]) -> str:
    for idx, line in enumerate(block):
        s = norm_space(line)

        if "競走成績" in s:
            for j in range(idx + 1, min(idx + 8, len(block))):
                t = norm_space(block[j])

                if not t:
                    continue
                if "第 " in t and "日" in t:
                    continue
                if re.search(r"\d{4}/\s*\d{1,2}/\d{1,2}", t):
                    continue
                if "ボートレース" in t and len(t) <= 12:
                    continue
                if "内容については主催者発行のものと照合して下さい" in t:
                    continue
                if "払戻金" in t:
                    continue

                return t

    for line in block[:8]:
        s = norm_space(line)
        if "［成績］" in s:
            m = re.search(r"［成績］\s+\d{1,2}/\d{1,2}\s+(.+?)\s+第\s*\d+日", s)
            if m:
                return norm_space(m.group(1))

    return ""


def normalize_finish(raw: str) -> Any:
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    return raw


def normalize_st(raw: str) -> str:
    s = str(raw or "").strip()
    m = re.match(r"^([0-9]+)\.([0-9]{2})$", s)
    if not m:
        return ""
    return f".{m.group(2)}"


def parse_result_row(line: str) -> Optional[Dict[str, Any]]:
    s = line.rstrip()
    m = RE_RESULT_ROW.match(s)
    if not m:
        return None

    finish_raw = m.group(1)
    reg = m.group(3)
    name = norm_space(m.group(4))
    course = int(m.group(8))
    st = normalize_st(m.group(9))

    return {
        "reg": reg,
        "name": name,
        "course": course,
        "st": st,
        "finish": normalize_finish(finish_raw),
    }


def parse_block(jcd: str, block: List[str]) -> Dict[str, Any]:
    venue = parse_venue(block)
    date = parse_date(block)
    day_no = parse_day_no(block)
    event_title = parse_event_title(block)
    event_title_norm = normalize_event_title(event_title)

    races: List[Dict[str, Any]] = []
    current_race: Optional[Dict[str, Any]] = None
    in_result_table = False

    for line in block:
        race_head = RE_RACE_HEADER.match(line)

        # H1800m 固定ではなく、H1200m / H1800m / Hxxxxm 全対応
        if race_head and RE_DISTANCE.search(line):
            if current_race:
                races.append(current_race)

            rno = int(race_head.group(1))
            current_race = {
                "rno": rno,
                "results": []
            }
            in_result_table = False
            continue

        if current_race is None:
            continue

        if "着 艇 登番" in line:
            in_result_table = True
            continue

        if in_result_table:
            row = parse_result_row(line)
            if row:
                current_race["results"].append(row)
                continue

            if (
                line.strip() == ""
                or line.strip().startswith("単勝")
                or "レース不成立" in line
                or "払戻金" in line
            ):
                in_result_table = False

    if current_race:
        races.append(current_race)

    return {
        "jcd": jcd,
        "venue": venue,
        "date": date,
        "day_no": day_no,
        "event_title_norm": event_title_norm,
        "races": races
    }


def main() -> None:
    files = collect_k_txt_files()
    if not files:
        raise FileNotFoundError("k結果txtが見つかりません。data/extract/k******.txt を確認してください。")

    out_items: List[Dict[str, Any]] = []

    for path in files:
        lines = read_text_auto(path)
        blocks = split_blocks(lines)

        for jcd, block in blocks:
            parsed = parse_block(jcd, block)
            if parsed["venue"] and parsed["races"]:
                out_items.append(parsed)

    out_items.sort(key=lambda x: (x.get("date") or "", x.get("jcd") or ""))

    payload = {
        "parsed_at": datetime.now(JST).isoformat(),
        "count": len(out_items),
        "venues": out_items
    }

    out_path = os.path.join("data", "k_results_parsed.json")
    os.makedirs("data", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print("files:", len(files))
    print("out:", out_path)
    print("venues:", len(out_items))


if __name__ == "__main__":
    main()