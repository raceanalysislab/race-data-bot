import json
import os

SRC = "data/mbrace_races_today.json"
OUT_DIR = "data/site/races"

os.makedirs(OUT_DIR, exist_ok=True)

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

for venue in data["venues"]:

    venue_name = venue["venue"]

    for race in venue["races"]:

        rno = race["rno"]

        out = {
            "venue": venue_name,
            "date": venue["date"],
            "race": race
        }

        fname = f"{venue_name}_{rno}R.json"
        path = os.path.join(OUT_DIR, fname)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

print("race json created")