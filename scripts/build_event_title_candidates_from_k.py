# scripts/build_event_title_candidates_from_k.py
# extract_k の k*.txt から開催タイトル候補を抽出して一覧化
#
# 出力:
#   data/k_event_title_candidates.json
#
# 目的:
# - 過去結果(kファイル)から開催名を広く拾う
# - normalize で「第○回」「○周年」を吸収した核タイトルを作る
# - manual に入れる材料を作る
#
# 方針:
# - KBGN / KEND ブロック単位で処理
# - 各ブロックの先頭付近だけ見て開催名を取る
# - ノイズ行は強めに除外
# - GitHub に載せられるサイズまで絞る

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

JST = timezone(timedelta(hours=9))

SRC_DIR = os.path.join("data", "extract_k")
OUT_PATH = os.path.join("data", "k_event_title_candidates.json")

MAX_RESULTS = 3000
MAX_SAMPLE_TITLES = 10
MAX_SAMPLE_FILES = 20
HEADER_SCAN_LINES = 30

TRANS = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "Ｒ": "R", "Ｈ": "H", "ｍ": "m", "：": ":", "　": " ",
    "％": "%", "－": "-", "―": "-", "−": "-",
    "Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III",
    "ａ": "a", "ｂ": "b", "ｃ": "c", "ｄ": "d", "ｅ": "e",
    "ｆ": "f", "ｇ": "g", "ｈ": "h", "ｉ": "i", "ｊ": "j",
    "ｋ": "k", "ｌ": "l", "ｍ": "m", "ｎ": "n", "ｏ": "o",
    "ｐ": "p", "ｑ": "q", "ｒ": "r", "ｓ": "s", "ｔ": "t",
    "ｕ": "u", "ｖ": "v", "ｗ": "w", "ｘ": "x", "ｙ": "y",
    "ｚ": "z",
    "Ａ": "A", "Ｂ": "B", "Ｃ": "C", "Ｄ": "D", "Ｅ": "E",
    "Ｆ": "F", "Ｇ": "G", "Ｈ": "H", "Ｉ": "I", "Ｊ": "J",
    "Ｋ": "K", "Ｌ": "L", "Ｍ": "M", "Ｎ": "N", "Ｏ": "O",
    "Ｐ": "P", "Ｑ": "Q", "Ｒ": "R", "Ｓ": "S", "Ｔ": "T",
    "Ｕ": "U", "Ｖ": "V", "Ｗ": "W", "Ｘ": "X", "Ｙ": "Y",
    "Ｚ": "Z",
})

RE_KBGN = re.compile(r"\b\d{2}KBGN\b")
RE_KEND = re.compile(r"\b\d{2}KEND\b")
RE_HEADER_LINE = re.compile(
    r"^\s*([^\[\]0-9]{1,8})\s*\[成績\]\s*\d{1,2}/\d{1,2}\s+(.+?)\s+第\s*\d+\s*日\s*$"
)

SKIP_EXACT_CONTAINS = [
    "データは、この場の全レース終了後に登録されます。",
    "内容については主催者発行のものと照合して下さい",
    "競走成績",
    "[払戻金]",
    "ボートレース",
]

SKIP_PATTERNS = [
    r"^\s*$",
    r"^\s*-{3,}\s*$",
    r"^\s*={3,}\s*$",
    r"^\s*\*{2,}.*\*{2,}\s*$",
    r"^\s*\[\s*払戻金\s*\]",
    r"^\s*単勝\b",
    r"^\s*複勝\b",
    r"^\s*2連単\b",
    r"^\s*2連複\b",
    r"^\s*3連単\b",
    r"^\s*3連複\b",
    r"^\s*拡連複\b",
    r"^\s*着\b",
    r"^\s*艇\b",
    r"^\s*登番\b",
    r"^\s*選手\b",
    r"^\s*進入\b",
    r"^\s*スタート\b",
    r"^\s*決まり手\b",
    r"^\s*返還\b",
    r"^\s*備考\b",
    r"^\s*\d{1,2}R\b",
    r"^\s*\d{4}/\s*\d{1,2}/\d{1,2}",
    r"^\s*\d{4}年\s*\d{1,2}月\s*\d{1,2}日",
    r"^\s*\d{1,2}/\d{1,2}\s*$",
]

SKIP_REGEXES = [re.compile(p) for p in SKIP_PATTERNS]


def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_event_title(s: str) -> str:
    s = norm(s)

    s = re.sub(r"\bSG\b", "", s)
    s = re.sub(r"\bG[123]\b", "", s)
    s = re.sub(r"第\s*\d+\s*回", "", s)
    s = re.sub(r"\d+\s*周年", "", s)

    s = re.sub(r"\s+", " ", s).strip()
    return s


def compact_event_title(s: str) -> str:
    return normalize_event_title(s).replace(" ", "")


def read_text_auto(path: str) -> List[str]:
    for enc in ["cp932", "utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.readlines()
        except Exception:
            pass
    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return f.readlines()


def split_blocks_k(lines_raw: List[str]) -> List[List[str]]:
    blocks: List[List[str]] = []
    cur: List[str] = []

    for raw in lines_raw:
        line = raw.rstrip("\n")

        if RE_KBGN.search(line):
            if cur:
                blocks.append(cur)
            cur = [line]
            continue

        cur.append(line)

        if RE_KEND.search(line):
            blocks.append(cur)
            cur = []

    if cur:
        blocks.append(cur)

    out: List[List[str]] = []
    for b in blocks:
        bb = [norm(x) for x in b if norm(x)]
        if bb:
            out.append(bb)
    return out


def is_skip_line(s: str) -> bool:
    if not s:
        return True

    for kw in SKIP_EXACT_CONTAINS:
        if kw in s:
            return True

    for rx in SKIP_REGEXES:
        if rx.search(s):
            return True

    return False


def clean_header_title(s: str) -> str:
    s = norm(s)
    s = re.sub(r"\s+第\s*\d+\s*日\s*$", "", s)
    s = re.sub(r"\s+\d{1,2}/\d{1,2}\s+", " ", s)
    s = re.sub(r"\[成績\]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def looks_like_event_title(s: str) -> bool:
    if is_skip_line(s):
        return False

    c = s.replace(" ", "")
    if len(c) < 4:
        return False

    keywords = [
        "杯", "賞", "記念", "カップ", "シリーズ", "選抜", "トロフィー",
        "決定戦", "競走", "大会", "チャレンジ", "ヴィーナス", "ルーキー",
        "マクール", "センプル", "MB大賞", "キングカップ",
    ]
    return any(k in s for k in keywords)


def parse_k_event_title(block: List[str]) -> Optional[str]:
    if not block:
        return None

    head = block[:HEADER_SCAN_LINES]

    # 優先1: [成績] ヘッダ行から抽出
    for line in head:
        m = RE_HEADER_LINE.match(line)
        if m:
            title = clean_header_title(m.group(2))
            if looks_like_event_title(title):
                return title

    # 優先2: 競走成績見出しの次の数行から抽出
    for i, line in enumerate(head):
        if "競走成績" not in line:
            continue

        for j in range(i + 1, min(i + 8, len(head))):
            cand = clean_header_title(head[j])
            if looks_like_event_title(cand):
                return cand

    # 優先3: 先頭付近からタイトルらしい行を拾う
    for line in head:
        cand = clean_header_title(line)
        if looks_like_event_title(cand):
            return cand

    return None


def extract_titles_from_file(path: str) -> List[str]:
    lines_raw = read_text_auto(path)
    blocks = split_blocks_k(lines_raw)

    out: List[str] = []
    for block in blocks:
        title = parse_k_event_title(block)
        if title:
            out.append(title)

    seen: Set[str] = set()
    uniq: List[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


def main():
    if not os.path.isdir(SRC_DIR):
        raise FileNotFoundError(f"not found dir: {SRC_DIR}")

    files = sorted(
        [os.path.join(SRC_DIR, fn) for fn in os.listdir(SRC_DIR) if re.match(r"^k\d{6}\.txt$", fn, re.IGNORECASE)]
    )

    grouped: Dict[str, Dict[str, object]] = defaultdict(lambda: {
        "title_key": "",
        "sample_titles": set(),
        "occurrences": 0,
        "sample_files": set(),
    })

    total_raw_titles = 0

    for path in files:
        titles = extract_titles_from_file(path)
        total_raw_titles += len(titles)

        for title in titles:
            key = compact_event_title(title)
            if not key:
                continue

            row = grouped[key]
            row["title_key"] = normalize_event_title(title)
            row["sample_titles"].add(title)
            row["occurrences"] += 1
            row["sample_files"].add(os.path.basename(path))

    results: List[Dict[str, object]] = []
    for _, row in grouped.items():
        results.append({
            "title_key": row["title_key"],
            "sample_titles": sorted(list(row["sample_titles"]))[:MAX_SAMPLE_TITLES],
            "occurrences": int(row["occurrences"]),
            "sample_files": sorted(list(row["sample_files"]))[:MAX_SAMPLE_FILES],
        })

    results.sort(key=lambda x: (-int(x["occurrences"]), str(x["title_key"])))
    total_unique_before_trim = len(results)
    results = results[:MAX_RESULTS]

    payload = {
        "_meta": {
            "generated_at": datetime.now(JST).isoformat(),
            "source_dir": SRC_DIR,
            "source_file_count": len(files),
            "raw_title_count": total_raw_titles,
            "unique_title_count_before_trim": total_unique_before_trim,
            "unique_title_count": len(results),
            "max_results": MAX_RESULTS,
            "header_scan_lines": HEADER_SCAN_LINES,
            "note": "extracted from KBGN/KEND block headers only",
        },
        "titles": results,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("out:", OUT_PATH)
    print("source_file_count:", len(files))
    print("raw_title_count:", total_raw_titles)
    print("unique_title_count_before_trim:", total_unique_before_trim)
    print("unique_title_count:", len(results))
    print("max_results:", MAX_RESULTS)


if __name__ == "__main__":
    main()