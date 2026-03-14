# scripts/build_event_master.py
# event_master_candidates.json → event_master.json
#
# 役割:
# - candidates の title_key を本番用 master に変換
# - grade / total_days を確定
# - notes 空欄のものもそのまま入れる
# - 将来は手修正した candidates をそのまま反映できる

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

JST = timezone(timedelta(hours=9))

SRC = "data/event_master_candidates.json"
DST = "data/event_master.json"


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def to_int_or_none(v: Any):
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None


def main():
    if not os.path.exists(SRC):
        raise FileNotFoundError(f"not found: {SRC}")

    src = load_json(SRC)
    titles = src.get("titles") or []

    master: Dict[str, Dict[str, Any]] = {}

    for row in titles:
        if not isinstance(row, dict):
            continue

        title_key = str(row.get("title_key") or "").strip()
        if not title_key:
            continue

        grade = str(row.get("grade_label") or "一般").strip() or "一般"
        total_days = to_int_or_none(row.get("confirmed_total_days"))
        notes = str(row.get("notes") or "").strip()

        sample_titles = row.get("sample_titles") or []
        venues = row.get("venues") or []

        master[title_key] = {
            "grade": grade,
            "total_days": total_days,
            "notes": notes,
            "sample_titles": sample_titles,
            "venues": venues,
        }

    payload = {
        "_meta": {
            "generated_at": datetime.now(JST).isoformat(),
            "source": SRC,
            "title_count": len(master),
        },
        "events": master,
    }

    os.makedirs("data", exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("out:", DST)
    print("title_count:", len(master))


if __name__ == "__main__":
    main()