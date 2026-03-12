import json
import pathlib
from collections import defaultdict

SRC = pathlib.Path("data/master/raw/fan2510.txt")
K_RESULTS = pathlib.Path("data/k_results_parsed.json")
OUT = pathlib.Path("data/master/players_master.json")

players = {}

def clean_name(s: str) -> str:
    return s.replace("　", "").strip()

# fanマスター（名前）
with open(SRC, "r", encoding="cp932", errors="ignore") as f:
    for line in f:
        if len(line) < 40:
            continue

        reg = line[0:4].strip()
        if not reg.isdigit():
            continue

        name = clean_name(line[4:12])

        players[reg] = {
            "reg": reg,
            "name": name,
            "starts": 0,
            "wins": 0,
            "top2": 0,
            "top3": 0,
            "courses": {str(i): {"starts":0,"wins":0} for i in range(1,7)}
        }

# k結果から成績作る
if K_RESULTS.exists():
    with open(K_RESULTS, "r", encoding="utf-8") as f:
        data = json.load(f)

    for venue in data["venues"]:
        for race in venue["races"]:
            for r in race["results"]:

                reg = r["reg"]
                if reg not in players:
                    continue

                finish = r["finish"]
                course = str(r["course"])

                p = players[reg]

                p["starts"] += 1

                if isinstance(finish, int):

                    if finish == 1:
                        p["wins"] += 1

                    if finish <= 2:
                        p["top2"] += 1

                    if finish <= 3:
                        p["top3"] += 1

                    p["courses"][course]["starts"] += 1

                    if finish == 1:
                        p["courses"][course]["wins"] += 1

# 最終率計算
for reg,p in players.items():

    starts = p["starts"]

    if starts > 0:
        p["win_rate"] = round(p["wins"]/starts*100,2)
        p["top2_rate"] = round(p["top2"]/starts*100,2)
        p["top3_rate"] = round(p["top3"]/starts*100,2)
    else:
        p["win_rate"] = 0
        p["top2_rate"] = 0
        p["top3_rate"] = 0

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players_master built:", len(players))