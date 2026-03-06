# scripts/parse_mbrace_txt.py
# mbrace番組表txt（STARTB...FINALB / xxBBGN...xxBEND 想定）→ 会場ごとにパースしてJSON化
# 出力: data/mbrace_races_today.json

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

TRANS = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "Ｒ": "R", "Ｈ": "H", "ｍ": "m", "：": ":", "　": " ",
    "％": "%", "－": "-", "―": "-", "−": "-",
})

def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

RE_RACE_HEAD = re.compile(
    r"^\s*([0-9]{1,2})R\s+(.+?)\s+(進入固定|進入自由)?\s*H?([0-9]{3,4})m.*?締切予定\s*([0-9]{1,2}:[0-9]{2})"
)

RE_YMD = re.compile(r"(\d{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日")
RE_MD  = re.compile(r"([0-9]{1,2})月\s*([0-9]{1,2})日")

RE_BBGN = re.compile(r"\b\d{2}BBGN\b")
RE_BEND = re.compile(r"\b\d{2}BEND\b")

RE_BOAT_PREFIX = re.compile(r"^\s*([1-6])\s+(\d{4})\s*(.*)$")

FLOAT = r"[0-9]+\.[0-9]{1,2}"
FLOATP = rf"{FLOAT}%?"

RE_TAIL = re.compile(
    rf"({FLOATP})\s+({FLOATP})\s+"
    rf"({FLOATP})\s+({FLOATP})\s+"
    rf"(\d{{1,3}})\s+({FLOATP})\s*"
    rf"(\d{{1,3}})\s+({FLOATP})\s*(.*)$"
)

RE_GRADE = re.compile(r"(A1|A2|B1|B2)\s*$")
RE_AGE_BRANCH_WEIGHT = re.compile(r"(\d{1,2})\s*([^\d\s]{2,6})\s*(\d{2})\s*$")

# ===== 日目抽出用 =====
# txt実データに合わせて「第 1日」「第1日」を最優先で拾う
RE_DAY_TEXT_1 = re.compile(r"第\s*([0-9]+)\s*日")
RE_DAY_TEXT_2 = re.compile(r"([0-9]+)\s*日目")
RE_TOTAL_DAYS_TEXT = re.compile(r"([0-9]+)\s*日間")
RE_DAY_SLASH = re.compile(r"([0-9]+)\s*/\s*([0-9]+)")

def read_text_auto(path: str) -> List[str]:
    for enc in ["cp932", "utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.readlines()
        except Exception:
            pass
    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return f.readlines()

def infer_txt_path() -> str:
    p = os.path.join("data", "source_final_url.txt")
    if os.path.exists(p):
        try:
            url = (open(p, "r", encoding="utf-8", errors="ignore").read() or "").strip()
            m = re.search(r"/b(\d{6})\.lzh", url)
            if m:
                yymmdd = m.group(1)
                guess = os.path.join("data", "extract", f"b{yymmdd}.txt")
                if os.path.exists(guess):
                    return guess
        except Exception:
            pass

    exdir = os.path.join("data", "extract")
    if os.path.isdir(exdir):
        cands = [fn for fn in os.listdir(exdir) if re.match(r"^b\d{6}\.txt$", fn, re.IGNORECASE)]
        if cands:
            cands.sort()
            return os.path.join(exdir, cands[-1])

    return os.path.join("data", "extract", "b260303.txt")

def split_blocks(lines_raw: List[str]) -> List[List[str]]:
    """
    福岡みたいに BBGN が付かない先頭会場があるため、
    BBGN以前の先頭部分も1ブロックとして拾う。
    """
    blocks: List[List[str]] = []
    cur: List[str] = []

    for raw in lines_raw:
        l = raw.rstrip("\n")

        if RE_BBGN.search(l):
            if cur:
                blocks.append(cur)
            cur = [l]
            continue

        cur.append(l)

        if RE_BEND.search(l):
            blocks.append(cur)
            cur = []

    if cur:
        blocks.append(cur)

    out: List[List[str]] = []
    for b in blocks:
        bb = [norm(x) for x in b if x.strip()]
        if bb:
            out.append(bb)
    return out

def parse_venue(block: List[str]) -> str:
    for l in block[:200]:
        if "ボートレース" not in l:
            continue
        s = l.replace("ボートレース", "").strip()

        m = re.search(r"\d{1,2}月", s)
        head = s[:m.start()] if m else s
        v = head.replace(" ", "").strip()
        if v:
            return v
    return ""

def parse_date(block: List[str]) -> str:
    for l in block[:300]:
        m = RE_YMD.search(l)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    for l in block[:340]:
        m2 = RE_MD.search(l)
        if m2:
            mo, d = m2.groups()
            y = datetime.now(JST).year
            return f"{y:04d}-{int(mo):02d}-{int(d):02d}"

    return ""

def parse_day_info(block: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """
    会場ブロック内から日目情報を拾う。
    想定:
      第3日
      第 3日
      3日目
      6日間
      3/6
    """
    current_day: Optional[int] = None
    total_days: Optional[int] = None

    for l in block[:160]:
        s = norm(l)

        if current_day is None:
            m = RE_DAY_TEXT_1.search(s)
            if m:
                try:
                    current_day = int(m.group(1))
                except Exception:
                    pass

        if current_day is None:
            m = RE_DAY_TEXT_2.search(s)
            if m:
                try:
                    current_day = int(m.group(1))
                except Exception:
                    pass

        if total_days is None:
            m = RE_TOTAL_DAYS_TEXT.search(s)
            if m:
                try:
                    total_days = int(m.group(1))
                except Exception:
                    pass

        if current_day is None or total_days is None:
            m = RE_DAY_SLASH.search(s)
            if m:
                try:
                    if current_day is None:
                        current_day = int(m.group(1))
                    if total_days is None:
                        total_days = int(m.group(2))
                except Exception:
                    pass

        if current_day is not None and total_days is not None:
            break

    return current_day, total_days

def format_day_label(current_day: Optional[int], total_days: Optional[int]) -> Optional[str]:
    if current_day is None:
        return None
    if current_day == 1:
        return "初日"
    if total_days is not None and current_day == total_days:
        return "最終日"
    return f"{current_day}日目"

def _to_float(x: str) -> Optional[float]:
    try:
        return float((x or "").replace("%", ""))
    except Exception:
        return None

def _to_int(x: str) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None

def _deglue_numbers(s: str) -> str:
    """
    motor_2 + boat_no の連結を分割
    例: 30.00156 -> 30.00 156
    """
    s = norm(s)

    for _ in range(4):
        s2 = re.sub(r"(\d+\.\d{1,2})(\d{2,3})(?=\s|$)", r"\1 \2", s)
        if s2 == s:
            break
        s = s2
    return s

def _parse_boat_line(line: str) -> Optional[Dict[str, Any]]:
    line = _deglue_numbers(line)
    mp = RE_BOAT_PREFIX.match(line)
    if not mp:
        return None

    waku = _to_int(mp.group(1))
    regno = _to_int(mp.group(2))
    rest_all = (mp.group(3) or "").strip()
    if not waku or not regno or not rest_all:
        return None

    rest_all = _deglue_numbers(rest_all)

    mt = RE_TAIL.search(rest_all)
    if not mt:
        return None

    nat_win  = _to_float(mt.group(1))
    nat_2    = _to_float(mt.group(2))
    loc_win  = _to_float(mt.group(3))
    loc_2    = _to_float(mt.group(4))
    motor_no = _to_int(mt.group(5))
    motor_2  = _to_float(mt.group(6))
    boat_no  = _to_int(mt.group(7))
    boat_2   = _to_float(mt.group(8))
    note     = (mt.group(9) or "").strip