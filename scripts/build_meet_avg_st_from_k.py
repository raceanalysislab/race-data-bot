# scripts/build_meet_avg_st_from_k.py

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

RE_KBGN = re.compile(r"^\d{2}KBGN$")
RE_KEND = re.compile(r"^\d{2}KEND$")
RE_DATE = re.compile(r"(\d{1,2})/(\d{1,2})")
RE_RACE_HEADER = re.compile(r"^\s*(\d{1,2})R")
RE_K_FILENAME = re.compile(r"^k(\d{2})(\d{2})(\d{2})\.txt$", re.IGNORECASE)

RE_RESULT_ROW_HEAD = re.compile(
    r"^\s*([0-9]{2}|S[0-9]|F|K0)\s+([1-6])\s+(\d{4})\s+(.+)$"
)

RE_RESULT_ROW_CANDIDATE = re.compile(
    r"^([0-9]{2}|S[0-9]|F|K0)\s+[1-6]\s+\d{4}\s+"
)


def norm_space(s: str) -> str:
    s = (s or "").replace("\u3000", " ")
    return re.sub(r"\s+", " ", s).strip()


def safe_filename_part(s: str) -> str:
    s = norm_space(s)
    for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
        s = s.replace(ch, "_")
    return s


def normalize_venue(s: str) -> str:
    s = s or ""
    s = s.replace("ボートレース", "")
    s = s.replace("\u3000", "")
    s = s.replace(" ", "")
    return s.strip()


def normalize_event_title(s: str) -> str:
    s = norm_space(s)
    s = s.replace("　", " ")
    s = re.sub(r"\s+", " ", s)
    s = s.replace("第４７回", "第47回")
    s = s.replace("第４８回", "第48回")
    s = s.replace("第１１th", "第11th")
    s = s.replace("１１th", "11th")
    s = s.replace("　", "")
    s = s.replace(" ", "")
    return s


def read_text_auto(path: str) -> List[str]:
    for enc in ["cp932", "utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return [x.rstrip("\n") for x in f]
        except Exception:
            pass
    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return [x.rstrip("\n") for x in f]


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
            raw = s.split("［成績］", 1)[0]
            return normalize_venue(raw)
    return ""


def infer_year_from_path(path: str) -> int:
    name = os.path.basename(path)
    m = RE_K_FILENAME.match(name)
    if m:
        yy = int(m.group(1))
        return 1900 + yy if yy >= 90 else 2000 + yy
    return datetime.now(JST).year


def parse_date(block: List[str], path: str) -> str:
    year = infer_year_from_path(path)

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


def list_k_txt_files() -> List[str]:
    candidates: List[str] = []
    search_dirs = [
        os.path.join("data", "extract_k"),
        os.path.join("data", "extract"),
        os.path.join("data"),
    ]

    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for fn in files:
                if re.match(r"^k\d{6}\.txt$", fn, re.IGNORECASE):
                    candidates.append(os.path.join(root, fn))

    return sorted(set(candidates))


def extract_name_from_tail(tail: str) -> str:
    m = re.match(r"(.+?)\s+\d+\s+\d+\s+", tail)
    if m:
        return norm_space(m.group(1))
    return norm_space(tail)


# ⭐ 修正① ST取得（列ズレ対応）
def extract_st_from_result_line(line: str) -> Tuple[Optional[float], bool, bool]:
    s = line.strip()

    if re.match(r"^\s*K0\s+", s):
        return None, False, False

    nums = re.findall(r"[FL]?\d+\.\d{2}", s)
    if not nums:
        return None, False, False

    st_raw = nums[-1]

    is_f = st_raw.startswith("F")
    is_l = st_raw.startswith("L")

    st_num = st_raw.lstrip("F").lstrip("L")

    try:
        return float(st_num), is_f, is_l
    except Exception:
        return None, is_f, is_l


def clear_output_dir(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for fn in os.listdir(out_dir):
        path = os.path.join(out_dir, fn)
        if os.path.isfile(path) and fn.lower().endswith(".json"):
            os.remove(path)


def better_payload(base: Dict[str, Any], challenger: Dict[str, Any]) -> Dict[str, Any]:
    base_count = int(base.get("player_count", 0) or 0)
    ch_count = int(challenger.get("player_count", 0) or 0)
    return challenger if ch_count > base_count else base


def main() -> None:
    paths = list_k_txt_files()
    if not paths:
        raise FileNotFoundError("k結果txtが見つかりません。data/extract_k を確認してください。")

    day_stats: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(
                lambda: {"st_sum": 0.0, "st_count": 0, "name": ""}
            )
        )
    )

    meet_meta: Dict[str, Dict[str, str]] = {}

    file_count = 0
    race_count = 0
    unmatched_rows = 0
    skipped_k0_rows = 0
    skipped_f_rows = 0
    skipped_l_rows = 0

    for path in paths:
        lines = read_text_auto(path)
        blocks = split_blocks(lines)
        file_count += 1

        for block in blocks:
            venue = parse_venue(block)
            date_str = parse_date(block, path)
            event_title_raw = parse_event_title(block)

            if not venue or not event_title_raw or not date_str:
                continue

            event_title_norm = normalize_event_title(event_title_raw)
            if not event_title_norm:
                continue

            meet_key = f"{venue}|{event_title_norm}"

            if meet_key not in meet_meta:
                meet_meta[meet_key] = {
                    "venue": venue,
                    "event_title": event_title_raw,
                    "event_title_norm": event_title_norm,
                }

            current_race = None
            in_result_table = False

            for line in block:
                race_head = RE_RACE_HEADER.match(line)
                if race_head and "H1800m" in line:
                    current_race = int(race_head.group(1))
                    in_result_table = False
                    race_count += 1
                    continue

                if current_race is None:
                    continue

                if "着 艇 登番" in line:
                    in_result_table = True
                    continue

                if in_result_table:
                    head = RE_RESULT_ROW_HEAD.match(line)
                    if head:
                        rank = str(head.group(1)).strip()
                        reg = str(head.group(3)).strip()
                        tail = str(head.group(4))
                        name = extract_name_from_tail(tail)

                        if rank == "K0":
                            skipped_k0_rows += 1
                            continue

                        st, is_f, is_l = extract_st_from_result_line(line)

                        if is_f:
                            skipped_f_rows += 1
                            continue

                        if is_l:
                            skipped_l_rows += 1
                            continue

                        if reg and st is not None:
                            day_stats[meet_key][date_str][reg]["st_sum"] += st
                            day_stats[meet_key][date_str][reg]["st_count"] += 1
                            if name:
                                day_stats[meet_key][date_str][reg]["name"] = name
                            continue

                        s = line.strip()
                        if s and RE_RESULT_ROW_CANDIDATE.match(s):
                            unmatched_rows += 1
                            print("UNMATCHED_RESULT_ROW:", s)
                        continue

                    # ⭐ 修正② 空行依存削除
                    if (
                        line.strip().startswith("単勝")
                        or "レース不成立" in line
                        or "払戻金" in line
                    ):
                        in_result_table = False

    # （以下は元コードそのまま）