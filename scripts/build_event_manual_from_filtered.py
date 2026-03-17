# scripts/build_event_manual_from_filtered.py
# filteredからG1だけ抽出してmanual生成

import json
import os

SRC = "data/k_event_title_candidates_filtered.json"
DST = "data/event_master_manual.json"

# G1判定キーワード
G1_KEYWORDS = [
    "周年記念",
    "開設",
    "キングカップ",
    "センプルカップ",
    "ダイヤモンドカップ",
]

def is_g1(title: str) -> bool:
    return any(k in title for k in G1_KEYWORDS)

def main():
    if not os.path.exists(SRC):
        raise FileNotFoundError(SRC)

    with open(SRC, "r", encoding="utf-8") as f:
        data = json.load(f)

    titles = data.get("titles", [])

    events = {}

    for row in titles:
        title = row.get("title_key", "")

        if not is_g1(title):
            continue

        events[title] = {
            "grade": "G1"
        }

    out = {
        "events": events
    }

    os.makedirs("data", exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("out:", DST)
    print("g1_count:", len(events))


if __name__ == "__main__":
    main()