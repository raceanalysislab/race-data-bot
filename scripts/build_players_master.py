import json
import pathlib

SRC = pathlib.Path("data/master/raw/fan2510.txt")
OUT = pathlib.Path("data/master/players_master.json")

players = {}

with open(SRC, "r", encoding="cp932", errors="ignore") as f:
    for line in f:
        if len(line) < 120:
            continue

        try:
            reg = line[0:4].strip()
            name = line[4:20].strip()

            if not reg.isdigit():
                continue

            players[reg] = {
                "reg": reg,
                "name": name
            }

        except:
            continue

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players_master built:", len(players))