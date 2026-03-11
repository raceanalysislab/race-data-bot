import json
import pathlib

PLAYERS_PATH = pathlib.Path("data/master/players_master.json")
ST_PATH = pathlib.Path("data/master/k_st_index.json")
OUT_PATH = pathlib.Path("data/master/merged_players.json")


def load_json(path: pathlib.Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


players = load_json(PLAYERS_PATH)
st_index = load_json(ST_PATH)

merged = {}

for reg, p in players.items():
    item = dict(p)

    st = st_index.get(reg)
    if st:
        item["avg_st"] = st.get("avg_st")
        item["st_count"] = st.get("count")

    merged[reg] = item

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

print("merged:", len(merged))