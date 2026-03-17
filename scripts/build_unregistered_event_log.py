import json
import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

SRC_DIR = "data"
OUT_PATH = os.path.join("data", "unregistered_event_titles.json")

KEYWORDS = [
    "記念", "周年", "MB大賞", "ヴィーナス", "ルーキー",
    "レディース", "ダービー", "グランプリ",
    "クラシック", "メモリアル", "チャレンジカップ"
]

def main():
    files = [
        f for f in os.listdir(SRC_DIR)
        if f.startswith("mbrace_races_") and f.endswith(".json")
    ]
    if not files:
        return

    files.sort()
    path = os.path.join(SRC_DIR, files[-1])

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out = []

    for v in data.get("venues", []):
        title = v.get("event_title", "")
        grade = v.get("grade_label", "")
        venue = v.get("venue", "")
        date = v.get("date", "")

        if grade != "一般":
            continue

        hit = None
        for kw in KEYWORDS:
            if kw in title:
                hit = kw
                break

        if not hit:
            continue

        out.append({
            "date": date,
            "venue": venue,
            "event_title": title,
            "current_grade": grade,
            "reason": f"keyword_hit: {hit}"
        })

    payload = {
        "_meta": {
            "generated_at": datetime.now(JST).isoformat(),
            "count": len(out)
        },
        "events": out
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("unregistered:", len(out))


if __name__ == "__main__":
    main()