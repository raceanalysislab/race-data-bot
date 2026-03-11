import json
import pathlib

SRC = pathlib.Path("data/master/raw/fan2510.txt")
OUT = pathlib.Path("data/master/players_master.json")

players = {}

with open(SRC, "r", encoding="cp932", errors="ignore") as f:
    for line in f:

        if len(line) < 100:
            continue

        reg = line[0:4].strip()

        if not reg.isdigit():
            continue

        name = line[4:20].strip()

        nat_win = line[20:26].strip()
        nat_2 = line[26:32].strip()
        nat_3 = line[32:38].strip()

        players[reg] = {
            "reg": reg,
            "name": name,
            "nat_win": nat_win,
            "nat_2": nat_2,
            "nat_3": nat_3
        }

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players_master built:", len(players))