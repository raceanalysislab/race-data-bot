import json
import pathlib

SRC = pathlib.Path("data/master/raw/fan2510.txt")
OUT = pathlib.Path("data/master/players_master.json")

players = {}

def clean_name(s: str) -> str:
    return s.replace("　", "").strip()

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
            "name": name
        }

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players_master built:", len(players))