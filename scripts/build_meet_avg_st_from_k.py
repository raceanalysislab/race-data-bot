# scripts/build_meet_avg_st_from_k.py
# extract_k 内の k******.txt を全部読んで
# 同一開催（会場 + 開催タイトル）ごとの
# 選手別「今節平均ST」を作る
#
# 出力:
#   data/meet_avg_st.json
#
# 使い方:
# - race-detail.js 側で
#   venue + event_title をキーにして参照
# - 各選手 regno ごとに avg_st / count を使う

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

JST = timezone(timedelta(hours=9))

RE_KBGN = re.compile(r"^\d{2}KBGN$")
RE_KEND = re.compile(r"^\d{2}KEND$")
RE_DATE = re.compile(r"(\d{1,2})/(\d{1,2})")
RE_RACE_HEADER = re.compile(r"^\s*(\d{1,2})R")
RE_RESULT_ROW = re.compile(
    r"^\s*([0-9]{2}|S[0-9]|F|K0)\s+([1-6])\s+(\d{4})\s+(.+?)\s+\d+\s+\d+\s+.*?\s+([0-9]+\.[0-9]{2})\s+"
)


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


def main() -> None:
    paths = list_k_txt_files()
    if not paths:
        raise FileNotFoundError("k結果txtが見つかりません。data/extract_k を確認してください。")

    # meet_key(会場|開催名) -> reg -> {st_sum, st_count, name}
    meet_stats: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(
        lambda: defaultdict(lambda: {"st_sum": 0.0, "st_count": 0, "name": ""})
    )

    file_count = 0
    race_count = 0

    for path in paths:
        lines = read_text_auto(path)
        blocks = split_blocks(lines)
        file_count += 1

        for block in blocks:
            venue = parse_venue(block)
            _date_str = parse_date(block)  # 読み取り自体は残す
            event_title = parse_event_title(block)

            if not venue or not event_title:
                continue

            meet_key = f"{venue}|{event_title}"

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
                    m = RE_RESULT_ROW.match(line)
                    if m:
                        reg = str(m.group(3)).strip()
                        name = norm_space(m.group(4))
                        st_raw = m.group(5)

                        try:
                            st = float(st_raw)
                        except Exception:
                            st = None

                        if reg and st is not None:
                            meet_stats[meet_key][reg]["st_sum"] += st
                            meet_stats[meet_key][reg]["st_count"] += 1
                            if name:
                                meet_stats[meet_key][reg]["name"] = name
                        continue

                    if (
                        line.strip() == ""
                        or line.strip().startswith("単勝")
                        or "レース不成立" in line
                        or "払戻金" in line
                    ):
                        in_result_table = False

    out_meets: Dict[str, Any] = {}

    for meet_key, regs in meet_stats.items():
        out_meets[meet_key] = {}
        for reg, src in regs.items():
            count = int(src["st_count"])
            avg_st = round(src["st_sum"] / count, 2) if count > 0 else None

            out_meets[meet_key][reg] = {
                "name": src["name"],
                "avg_st": avg_st,
                "count": count
            }

    payload = {
        "generated_at": datetime.now(JST).isoformat(),
        "source_files": file_count,
        "race_count": race_count,
        "meet_count": len(out_meets),
        "meets": out_meets
    }

    out_path = os.path.join("data", "meet_avg_st.json")
    os.makedirs("data", exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("files:", file_count)
    print("races:", race_count)
    print("meets:", len(out_meets))
    print("out:", out_path)


if __name__ == "__main__":
    main()