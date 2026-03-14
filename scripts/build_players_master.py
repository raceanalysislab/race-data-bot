import json
import pathlib

NAME_MASTER = pathlib.Path("data/master/players_name_master.json")
K_RESULTS = pathlib.Path("data/k_results_parsed.json")
OUT = pathlib.Path("data/master/players_master.json")

players = {}


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# 名前DB読み込み
name_master = load_json(NAME_MASTER, {})

for reg, row in name_master.items():
    players[reg] = {
        "reg": reg,
        "name": row["name"],
        "sei": row["sei"],
        "mei": row["mei"],
        "starts": 0,
        "wins": 0,
        "top2": 0,
        "top3": 0,
        "courses": {str(i): {"starts": 0, "wins": 0} for i in range(1, 7)}
    }


# 成績計算
if K_RESULTS.exists():
    data = load_json(K_RESULTS, {})

    for venue in data.get("venues", []):
        for race in venue.get("races", []):
            for r in race.get("results", []):

                reg = str(r.get("reg", "")).strip()
                if reg not in players:
                    continue

                finish = r.get("finish")
                course = str(r.get("course", "")).strip()

                p = players[reg]
                p["starts"] += 1

                if isinstance(finish, int):

                    if finish == 1:
                        p["wins"] += 1

                    if finish <= 2:
                        p["top2"] += 1

                    if finish <= 3:
                        p["top3"] += 1

                    if course in p["courses"]:
                        p["courses"][course]["starts"] += 1

                        if finish == 1:
                            p["courses"][course]["wins"] += 1


# 勝率計算
for reg, p in players.items():

    starts = p["starts"]

    if starts > 0:
        p["win_rate"] = round(p["wins"] / starts * 100, 2)
        p["top2_rate"] = round(p["top2"] / starts * 100, 2)
        p["top3_rate"] = round(p["top3"] / starts * 100, 2)
    else:
        p["win_rate"] = 0
        p["top2_rate"] = 0
        p["top3_rate"] = 0


OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players loaded:", len(players))
print("players_master built")