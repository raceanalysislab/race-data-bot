import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

JST = timezone(timedelta(hours=9))

RE_KBGN = re.compile(r"^\d{2}KBGN$")
RE_KEND = re.compile(r"^\d{2}KEND$")
RE_DATE = re.compile(r"(\d{1,2})/(\d{1,2})")
RE_RACE_HEADER = re.compile(r"^\s*(\d{1,2})R")
RE_RESULT_ROW = re.compile(
    r"^\s*([0-9]{2}|S[0-9]|F|K0)\s+([1-6])\s+(\d{4})\s+(.+?)\s+\d+\s+\d+\s+"
)

VALID_KIMARITE = {
    "逃げ",
    "差し",
    "まくり",
    "まくり差し",
    "抜き",
    "恵まれ",
}


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def read_text_auto(path: str) -> List[str]:
    for enc in ["cp932", "utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return [x.rstrip("\n") for x in f]
        except Exception:
            pass
    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return [x.rstrip("\n") for x in f]


def _find_latest_k_txt() -> Optional[str]:
    search_dirs = [
        os.path.join("data", "extract"),
        os.path.join("data"),
    ]

    cands: List[str] = []

    for base in search_dirs:
        if not os.path.isdir(base):
            continue

        for root, _, files in os.walk(base):
            for fn in files:
                if re.match(r"^k\d{6}\.txt$", fn, re.IGNORECASE):
                    cands.append(os.path.join(root, fn))

    if not cands:
        return None

    cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return cands[0]


def infer_txt_path() -> str:
    p = os.path.join("data", "source_final_url_k.txt")

    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                url = f.read().strip()

            m = re.search(r"/k(\d{6})\.lzh", url, re.IGNORECASE)
            if m:
                yymmdd = m.group(1)

                guesses = [
                    os.path.join("data", "extract", f"k{yymmdd}.txt"),
                    os.path.join("data", f"k{yymmdd}.txt"),
                ]

                for guess in guesses:
                    if os.path.exists(guess):
                        return guess
        except Exception:
            pass

    latest = _find_latest_k_txt()
    if latest:
        return latest

    raise FileNotFoundError(
        "k結果txtが見つかりません。"
        " data/source_final_url_k.txt または data/extract/k******.txt を確認してください。"
    )


def split_blocks(lines: List[str]) -> List[List[str]]:
    blocks: List[List[str]] = []
    cur: List[str] = []

    for line in lines:
        if RE_KBGN.match(line.strip()):
            if cur:
                blocks.append(cur)
            cur = [line]
            continue

        cur.append(line)

        if RE_KEND.match(line.strip()):
            blocks.append(cur)
            cur = []

    if cur:
        blocks.append(cur)

    return [b for b in blocks if b]


def parse_venue(block: List[str]) -> str:
    for line in block[:8]:
        s = norm_space(line)
        if "［成績］" in s:
            return s.split("［成績］", 1)[0].replace(" ", "")
    return ""


def parse_date(block: List[str]) -> str:
    year = datetime.now(JST).year

    for line in block[:30]:
        m = RE_DATE.search(line)
        if m:
            mm, dd = m.groups()
            return f"{year:04d}-{int(mm):02d}-{int(dd):02d}"

    return ""


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


def normalize_course(value: int) -> int:
    return int(value)


def extract_kimarite_nearby(block: List[str], header_idx: int) -> str:
    start = max(0, header_idx - 6)
    end = min(len(block), header_idx + 20)

    for i in range(start, end):
        s = norm_space(block[i])
        if s in VALID_KIMARITE:
            return s

        for k in VALID_KIMARITE:
            if k in s:
                return k

    return ""


def parse_race_title(line: str, rno: int) -> str:
    s = line.rstrip()
    m = re.match(rf"^\s*{rno}R\s+(.+?)\s+H1800m", s)
    if m:
        return norm_space(m.group(1))

    s2 = re.sub(rf"^\s*{rno}R\s+", "", s)
    s2 = re.sub(r"\s+H1800m.*$", "", s2)
    return norm_space(s2)


def parse_block(block: List[str]) -> Dict[str, Any]:
    venue = parse_venue(block)
    date = parse_date(block)
    event_title = parse_event_title(block)

    races: List[Dict[str, Any]] = []
    current_race: Optional[Dict[str, Any]] = None
    in_result_table = False

    for idx, line in enumerate(block):
        race_head = RE_RACE_HEADER.match(line)
        if race_head and "H1800m" in line:
            if current_race:
                races.append(current_race)

            rno = int(race_head.group(1))
            current_race = {
                "rno": rno,
                "race_title": parse_race_title(line, rno),
                "label": extract_kimarite_nearby(block, idx),
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
            m = RE_RESULT_ROW.match(line)
            if m:
                finish_raw = m.group(1)
                boat_no = int(m.group(2))
                reg = m.group(3)
                name = norm_space(m.group(4))

                current_race["results"].append({
                    "reg": reg,
                    "name": name,
                    "boat": boat_no,
                    "course": normalize_course(boat_no),
                    "finish": normalize_finish(finish_raw)
                })
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
        "venue": venue,
        "date": date,
        "event_title": event_title,
        "races": races
    }


def main():
    txt_path = infer_txt_path()
    lines = read_text_auto(txt_path)
    blocks = split_blocks(lines)

    out_blocks: List[Dict[str, Any]] = []
    for block in blocks:
        parsed = parse_block(block)
        if parsed["venue"] and parsed["races"]:
            out_blocks.append(parsed)

    payload = {
        "source": os.path.basename(txt_path),
        "parsed_at": datetime.now(JST).isoformat(),
        "venues": out_blocks
    }

    out_path = os.path.join("data", "k_results_parsed.json")
    os.makedirs("data", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("txt:", txt_path)
    print("out:", out_path)
    print("venues:", len(out_blocks))


if __name__ == "__main__":
    main()