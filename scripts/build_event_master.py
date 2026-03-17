# scripts/build_event_master.py
# candidates + manual → event_master.json
#
# 長期運用方針:
# - candidates は開催名候補の自動収集専用
# - candidates の grade_label は本番採用しない
# - grade の確定値は manual のみで持つ
# - manual に無いものは既定で「一般」

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

JST = timezone(timedelta(hours=9))

CANDIDATES = "data/event_master_candidates.json"
MANUAL = "data/event_master_manual.json"
DST = "data/event_master.json"


def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
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
    src = load_json(CANDIDATES)
    manual = load_json(MANUAL)

    titles = src.get("titles") or []
    manual_events = manual.get("events") or {}

    master: Dict[str, Dict[str, Any]] = {}

    # --- ① candidates をベースに作る ---
    # grade は candidates を信用せず、既定値は常に「一般」
    for row in titles:
        if not isinstance(row, dict):
            continue

        title_key = str(row.get("title_key") or "").strip()
        if not title_key:
            continue

        grade = "一般"
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

    # --- ② manual で上書き（最重要） ---
    for title_key, override in manual_events.items():
        if not isinstance(override, dict):
            continue

        if title_key not in master:
            master[title_key] = {
                "grade": "一般",
                "total_days": None,
                "notes": "",
                "sample_titles": [],
                "venues": [],
            }

        base = master[title_key]

        base["grade"] = str(override.get("grade", base.get("grade", "一般")) or "一般").strip() or "一般"
        base["total_days"] = to_int_or_none(override.get("total_days", base.get("total_days")))
        base["notes"] = str(override.get("notes", base.get("notes", "")) or "").strip()
        base["sample_titles"] = override.get("sample_titles", base.get("sample_titles", [])) or []
        base["venues"] = override.get("venues", base.get("venues", [])) or []

        master[title_key] = base

    payload = {
        "_meta": {
            "generated_at": datetime.now(JST).isoformat(),
            "source_candidates": CANDIDATES,
            "source_manual": MANUAL,
            "title_count": len(master),
            "grade_policy": "manual_only_default_ippan",
        },
        "events": master,
    }

    os.makedirs("data", exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("out:", DST)
    print("title_count:", len(master))
    print("grade_policy: manual_only_default_ippan")


if __name__ == "__main__":
    main()