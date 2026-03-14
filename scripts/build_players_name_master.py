import json
import pathlib

SRC = pathlib.Path("data/master/raw/fan2510.txt")
OUT = pathlib.Path("data/master/players_name_master.json")


def clean_name(s: str) -> str:
    return str(s or "").replace("　", "").replace(" ", "").strip()


def split_name(name: str):
    name = clean_name(name)

    if not name:
        return "", ""

    n = len(name)

    if n == 1:
        return name, ""

    if n == 2:
        return name[:1], name[1:]

    if n == 3:
        return name[:1], name[1:]

    if n == 4:
        return name[:2], name[2:]

    if n == 5:
        return name[:2], name[2:]

    if n == 6:
        return name[:3], name[3:]

    return name[:-2], name[-2:]


players = {}

with open(SRC, "r", encoding="cp932", errors="ignore") as f:
    for line in f:

        if len(line) < 40:
            continue

        reg = line[0:4].strip()

        if not reg.isdigit():
            continue

        name = clean_name(line[4:12])
        sei, mei = split_name(name)

        players[reg] = {
            "reg": reg,
            "name": name,
            "sei": sei,
            "mei": mei
        }


OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players_name_master built:", len(players))