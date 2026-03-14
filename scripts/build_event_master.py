# scripts/build_event_master.py
# event_master_candidates.json → event_master.json

import json
import os

SRC = "data/event_master_candidates.json"
DST = "data/event_master.json"

def main():

    if not os.path.exists(SRC):
        raise FileNotFoundError("event_master_candidates.json not found")

    data = json.load(open(SRC, encoding="utf-8"))

    titles = data.get("titles", [])

    master = {}

    for row in titles:

        title_key = row.get("title_key")
        grade = row.get("grade_label")
        total_days = row.get("confirmed_total_days")

        if not title_key:
            continue

        master[title_key] = {
            "grade": grade or "一般",
            "total_days": total_days
        }

    os.makedirs("data", exist_ok=True)

    with open(DST, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)

    print("event master built:", len(master))


if __name__ == "__main__":
    main()