import json
import pathlib

PLAYERS_PATH = pathlib.Path("data/master/players_master.json")
ST_PATH = pathlib.Path("data/master/k_st_index.json")
OUT_PATH = pathlib.Path("data/master/merged_players.json")


def load_json(path: pathlib.Path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


players = load_json(PLAYERS_PATH)
st_index = load_json(ST_PATH)

merged = {}

for reg, p in players.items():

    item = dict(p)

    # ST指数
    st = st_index.get(reg)
    if st:
        item["avg_st"] = st.get("avg_st")
        item["st_count"] = st.get("count")

    # コース率計算
    courses = item.get("courses", {})
    course_rates = {}

    for c, v in courses.items():

        starts = v.get("starts", 0)
        wins = v.get("wins", 0)

        if starts > 0:
            win_rate = round(wins / starts * 100, 2)
        else:
            win_rate = 0

        course_rates[c] = {
            "starts": starts,
            "wins": wins,
            "win_rate": win_rate
        }

    item["course_stats"] = course_rates

    merged[reg] = item


OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

print("merged:", len(merged))