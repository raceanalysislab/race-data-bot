import json
import os

SRC = "data/mbrace_races_today.json"
OUT = "data/site/races"

os.makedirs(OUT, exist_ok=True)

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

count = 0

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

        path = os.path.join(OUT, fname)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        count += 1

print("created:", count, "race json files")