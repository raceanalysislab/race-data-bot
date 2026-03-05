import json
import os

MBRACE_PATH = "data/mbrace_races_today.json"
VENUES_PATH = "data/venues_today.json"

OUT_DIR = "data/site"
OUT_VENUES = os.path.join(OUT_DIR, "venues.json")
OUT_VENUE_DIR = os.path.join(OUT_DIR, "venues")

os.makedirs(OUT_VENUE_DIR, exist_ok=True)

with open(MBRACE_PATH, encoding="utf-8") as f:
    mbrace = json.load(f)

with open(VENUES_PATH, encoding="utf-8") as f:
    venues_today = json.load(f)

# --- venues.json (トップ用) ---
site_venues = []

for v in venues_today["venues"]:
    if not v["held"]:
        continue

    site_venues.append({
        "name": v["name"],
        "jcd": v["jcd"],
        "next_race": v["next_race"],
        "next_display": v["next_display"]
    })

with open(OUT_VENUES, "w", encoding="utf-8") as f:
    json.dump(site_venues, f, ensure_ascii=False, indent=2)

# --- 会場ごとのレース ---
for venue in mbrace["venues"]:

    venue_name = venue["venue"]

    races_out = []

    for r in venue["races"]:
        races_out.append({
            "rno": r["rno"],
            "name": r["name"],
            "cutoff": r["cutoff"],
            "distance": r["distance_m"]
        })

    path = os.path.join(OUT_VENUE_DIR, f"{venue_name}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "venue": venue_name,
            "date": venue["date"],
            "races": races_out
        }, f, ensure_ascii=False, indent=2)

print("site json build complete")