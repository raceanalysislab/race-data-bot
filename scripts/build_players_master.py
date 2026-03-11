import json
import pathlib
import re

SRC = pathlib.Path("data/master/raw/fan2510.txt")
OUT = pathlib.Path("data/master/players_master.json")

players = {}

with open(SRC, "r", encoding="cp932", errors="ignore") as f:
    for line in f:

        line = line.strip()

        m = re.match(r"^(\d{4})\s+([^\s]+)", line)
        if not m:
            continue

        reg = m.group(1)
        name = m.group(2)

        players[reg] = {
            "reg": reg,
            "name": name
        }

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players_master built:", len(players))