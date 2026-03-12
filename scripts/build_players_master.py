import json
import pathlib

SRC = pathlib.Path("data/master/raw/fan2510.txt")
OUT = pathlib.Path("data/master/players_master.json")

players = {}

def clean_name(s: str) -> str:
    return s.replace("　", "").strip()

with open(SRC, "r", encoding="cp932", errors="ignore") as f:
    for line in f:
        if len(line) < 60:
            continue

        reg = line[0:4].strip()
        if not reg.isdigit():
            continue

        name = clean_name(line[4:12])

        # デバッグ（桁確認）
        if reg == "3024":
            print(line)
            print("26:31 =", repr(line[26:31]))
            print("31:36 =", repr(line[31:36]))
            print("36:41 =", repr(line[36:41]))

        nat_3_raw = line[36:41].strip()

        try:
            nat_3 = round(int(nat_3_raw) / 1000, 2)
        except:
            nat_3 = None

        players[reg] = {
            "reg": reg,
            "name": name,
            "nat_3": nat_3
        }

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players_master built:", len(players))