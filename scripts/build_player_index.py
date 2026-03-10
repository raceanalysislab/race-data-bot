import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "mbrace_races_today.json"
DST = ROOT / "data" / "player_index_today.json"

VENUE_NAME_TO_JCD = {
    "桐生": "01",
    "戸田": "02",
    "江戸川": "03",
    "平和島": "04",
    "多摩川": "05",
    "浜名湖": "06",
    "蒲郡": "07",
    "常滑": "08",
    "津": "09",
    "三国": "10",
    "びわこ": "11",
    "住之江": "12",
    "尼崎": "13",
    "鳴門": "14",
    "丸亀": "15",
    "児島": "16",
    "宮島": "17",
    "徳山": "18",
    "下関": "19",
    "若松": "20",
    "芦屋": "21",
    "福岡": "22",
    "唐津": "23",
    "大村": "24",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def pick(d: dict, *keys, default=""):
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return default


def normalize_reg_no(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_name(value):
    return str(value or "").strip()


def normalize_race_no(value):
    s = str(value or "").strip().upper().replace("Ｒ", "R")
    if s.endswith("R"):
        s = s[:-1]
    try:
        return int(s)
    except Exception:
        return None


def extract_boats(race_obj):
    boats = pick(race_obj, "boats", "entries", default=[])
    return boats if isinstance(boats, list) else []


def extract_day_label(venue_obj):
    return str(pick(venue_obj, "day_label", "day", default="")).strip()


def main():
    src = load_json(SRC)

    player_index = []
    seen = set()

    venues = src if isinstance(src, list) else src.get("venues", [])
    if not isinstance(venues, list):
        venues = []

    for venue_obj in venues:
        venue_name = str(
            pick(venue_obj, "venue_name", "name", "venue", default="")
        ).strip()
        if not venue_name:
            continue

        jcd = str(
            pick(venue_obj, "jcd", default=VENUE_NAME_TO_JCD.get(venue_name, ""))
        ).zfill(2) if pick(venue_obj, "jcd", default=VENUE_NAME_TO_JCD.get(venue_name, "")) else VENUE_NAME_TO_JCD.get(venue_name, "")

        races = pick(venue_obj, "races", default=[])
        if not isinstance(races, list):
            continue

        for race_obj in races:
            race_no = normalize_race_no(
                pick(race_obj, "race", "race_no", "race_number", "number")
            )
            if not race_no:
                continue

            race_title = str(
                pick(race_obj, "race_title", "title", "race_name", default="")
            ).strip()

            boats = extract_boats(race_obj)

            for boat in boats:
                reg_no = normalize_reg_no(
                    pick(boat, "reg_no", "regno", "player_id", "toban")
                )
                name = normalize_name(
                    pick(boat, "name", "player_name", "senshu_name")
                )
                lane = pick(boat, "lane", "waku", "teiban", default="")

                if not reg_no or not name:
                    continue

                unique_key = (reg_no, venue_name, race_no)
                if unique_key in seen:
                    continue
                seen.add(unique_key)

                player_index.append({
                    "reg_no": reg_no,
                    "name": name,
                    "venue": venue_name,
                    "race": race_no,
                    "jcd": jcd,
                    "lane": int(lane) if str(lane).isdigit() else "",
                    "race_title": race_title,
                    "day_label": extract_day_label(venue_obj),
                })

    player_index.sort(key=lambda x: (x["name"], x["venue"], x["race"], x["lane"] or 99))

    with DST.open("w", encoding="utf-8") as f:
        json.dump(player_index, f, ensure_ascii=False, indent=2)

    print(f"written: {DST}")
    print(f"players: {len(player_index)}")


if __name__ == "__main__":
    main()