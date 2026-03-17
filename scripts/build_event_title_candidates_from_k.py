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
# - まずは広く拾う
# - 誤爆は後で消す
# - grade 判定はまだしない（タイトル母集団づくり優先）

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

JST = timezone(timedelta(hours=9))

SRC_DIR = os.path.join("data", "extract_k")
OUT_PATH = os.path.join("data", "k_event_title_candidates.json")

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

# ざっくり除外したい行
SKIP_PATTERNS = [
    r"^\s*$",
    r"^\s*-{3,}\s*$",
    r"^\s*={3,}\s*$",
    r"^\s*\*{2,}.*\*{2,}\s*$",
    r"^\s*ボートレース",
    r"^\s*競走成績",
    r"^\s*開催日",
    r"^\s*月日",
    r"^\s*天候",
    r"^\s*風",
    r"^\s*波",
    r"^\s*レース",
    r"^\s*R\s",
    r"^\s*\d{1,2}R\b",
    r"^\s*着\b",
    r"^\s*艇\b",
    r"^\s*選手\b",
    r"^\s*払戻\b",
    r"^\s*単勝\b",
    r"^\s*複勝\b",
    r"^\s*2連単\b",
    r"^\s*2連複\b",
    r"^\s*3連単\b",
    r"^\s*3連複\b",
    r"^\s*拡連複\b",
    r"^\s*進入\b",
    r"^\s*スタート\b",
    r"^\s*決まり手\b",
    r"^\s*返還\b",
    r"^\s*備考\b",
    r"^\s*\d{4}年\s*\d{1,2}月\s*\d{1,2}日",
    r"^\s*\d{1,2}月\s*\d{1,2}日",
]

SKIP_REGEXES = [re.compile(p) for p in SKIP_PATTERNS]


def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_event_title(s: str) -> str:
    s = norm(s)

    # グレード記号は照合ノイズとして除去
    s = re.sub(r"\bSG\b", "", s)
    s = re.sub(r"\bG[123]\b", "", s)

    # 回数・周年は年変動のため吸収
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


def is_skip_line(s: str) -> bool:
    for rx in SKIP_REGEXES:
        if rx.search(s):
            return True
    return False


def maybe_title_line(s: str) -> bool:
    # 広めに拾う
    if is_skip_line(s):
        return False

    c = s.replace(" ", "")
    if len(c) < 4:
        return False

    # 数字だけっぽいものは除外
    if re.fullmatch(r"[\d\.\-:/]+", c):
        return False

    # 選手行っぽいもの除外
    if re.match(r"^[1-6]\s+\d{4}", s):
        return False

    # よくある開催名キーワードを優先
    keywords = [
        "杯", "賞", "記念", "カップ", "シリーズ", "選抜", "トロフィー",
        "決定戦", "競走", "大会", "チャレンジ", "ヴィーナス", "ルーキー",
        "マクール", "センプル", "MB大賞", "キングカップ",
    ]
    if any(k in s for k in keywords):
        return True

    # 英数＋日本語の長め行も候補にする
    if re.search(r"[一-龥ぁ-んァ-ヶA-Za-z]", s) and len(c) >= 8:
        return True

    return False


def extract_titles_from_file(path: str) -> List[str]:
    lines = [norm(x) for x in read_text_auto(path)]
    out: List[str] = []

    for line in lines:
        if not maybe_title_line(line):
            continue

        # 行頭の会場名だけの残骸っぽいものは除外
        if len(line) <= 3:
            continue

        out.append(line)

    # 同一ファイル内重複削除
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
            "sample_titles": sorted(list(row["sample_titles"]))[:10],
            "occurrences": int(row["occurrences"]),
            "sample_files": sorted(list(row["sample_files"]))[:20],
        })

    results.sort(key=lambda x: (-int(x["occurrences"]), str(x["title_key"])))

    payload = {
        "_meta": {
            "generated_at": datetime.now(JST).isoformat(),
            "source_dir": SRC_DIR,
            "source_file_count": len(files),
            "raw_title_count": total_raw_titles,
            "unique_title_count": len(results),
            "note": "broad extraction from k files; review and prune false positives",
        },
        "titles": results,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("out:", OUT_PATH)
    print("source_file_count:", len(files))
    print("raw_title_count:", total_raw_titles)
    print("unique_title_count:", len(results))


if __name__ == "__main__":
    main()