# scripts/build_event_manual_from_grade_candidates.py
# event_grade_candidates.json から event_master_manual.json を生成
#
# 方針:
# - SG / G2 / G3 はそのまま採用
# - G1 は本場G1っぽいものだけ採用
# - BTS / BP / ボートピア / ウィンボ / エディウィン などは除外
# - 最後は人が manual を見て微修正する前提

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

JST = timezone(timedelta(hours=9))

SRC = "data/event_grade_candidates.json"
DST = "data/event_master_manual.json"

# G1でも manual 自動採用から外すもの
G1_EXCLUDE_KEYWORDS = [
    "BTS",
    "BP",
    "ボートピア",
    "オラレ",
    "外向発売所",
    "ウィンボ",
    "エディウィン",
    "劇場",
    "発売所",
]

# G1で積極採用する強い語
G1_INCLUDE_KEYWORDS = [
    "開設記念",
    "周年記念",
    "キングカップ",
    "センプルカップ",
    "王座決定戦",
    "王者決定戦",
    "覇者決定戦",
    "チャンピオンカップ",
    "太閤賞",
    "京極賞",
    "大渦大賞",
    "クラウン争奪戦",
    "北陸艇王決戦",
    "海の王者決定戦",
    "海響王決定戦",
    "びわこ大賞",
    "ツッキー王座決定戦",
    "赤城雷神杯",
    "競帝王決定戦",
]

def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def contains_any(title: str, keywords: List[str]) -> bool:
    return any(k in title for k in keywords)

def should_adopt(title: str, grade: str) -> bool:
    if grade in ("SG", "G2", "G3"):
        return True

    if grade == "G1":
        if contains_any(title, G1_EXCLUDE_KEYWORDS):
            return False
        if contains_any(title, G1_INCLUDE_KEYWORDS):
            return True
        return False

    return False

def main():
    src = load_json(SRC)
    rows = src.get("titles") or []

    events: Dict[str, Dict[str, Any]] = {}

    adopted_count = 0
    skipped_count = 0

    for row in rows:
        if not isinstance(row, dict):
            continue

        title = str(row.get("title_key") or "").strip()
        grade = str(row.get("suggested_grade") or "").strip()

        if not title or not grade:
            continue

        if not should_adopt(title, grade):
            skipped_count += 1
            continue

        sample_titles = row.get("sample_titles") or []
        sample_files = row.get("sample_files") or []

        notes = ""
        if sample_files:
            notes = f"auto_from_grade_candidates: {', '.join(sample_files[:5])}"

        events[title] = {
            "grade": grade,
            "total_days": None,
            "notes": notes,
            "sample_titles": sample_titles[:10],
            "venues": [],
        }
        adopted_count += 1

    payload = {
        "_meta": {
            "generated_at": datetime.now(JST).isoformat(),
            "source": SRC,
            "policy": "SG_G2_G3_direct_adopt_G1_filtered",
            "event_count": len(events),
            "adopted_count": adopted_count,
            "skipped_count": skipped_count,
        },
        "events": events,
    }

    os.makedirs("data", exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("out:", DST)
    print("event_count:", len(events))
    print("adopted_count:", adopted_count)
    print("skipped_count:", skipped_count)

if __name__ == "__main__":
    main()