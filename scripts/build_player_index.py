import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RACES_DIR = ROOT / "data" / "site" / "races"
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


def normalize_jcd(value, venue_name=""):
    v = "".join(ch for ch in str(value or "") if ch.isdigit())
    if v:
        return v.zfill(2)
    return VENUE_NAME_TO_JCD.get(str(venue_name or "").strip(), "")


def extract_boats(race_root: dict):
    race_obj = pick(race_root, "race", default={})
    if isinstance(race_obj, dict):
        boats = pick(race_obj, "boats", "entries", default=[])
        if isinstance(boats, list):
            return boats
    boats = pick(race_root, "boats", "entries", default=[])
    return boats if isinstance(boats, list) else []


def extract_race_no(data: dict, path: Path):
    race_no = normalize_race_no(
        pick(
            data,
            "race_no",
            "race",
            "race_number",
            "number",
            default=""
        )
    )
    if race_no:
        return race_no

    race_obj = pick(data, "race", default={})
    if isinstance(race_obj, dict):
        race_no = normalize_race_no(
            pick(
                race_obj,
                "race_no",
                "race",
                "race_number",
                "number",
                default=""
            )
        )
        if race_no:
            return race_no

    stem = path.stem
    tail = stem.split("_")[-1]
    return normalize_race_no(tail)


def extract_venue_name(data: dict):
    race_obj = pick(data, "race", default={})
    if isinstance(race_obj, dict):
        venue_name = str(
            pick(race_obj, "venue_name", "name", "venue", default="")
        ).strip()
        if venue_name:
            return venue_name

    return str(
        pick(data, "venue_name", "name", "venue", default="")
    ).strip()


def extract_day_label(data: dict):
    race_obj = pick(data, "race", default={})
    if isinstance(race_obj, dict):
        day_label = str(
            pick(race_obj, "day_label", "day", default="")
        ).strip()
        if day_label:
            return day_label

    return str(
        pick(data, "day_label", "day", default="")
    ).strip()


def extract_race_title(data: dict):
    race_obj = pick(data, "race", default={})
    if isinstance(race_obj, dict):
        race_title = str(
            pick(race_obj, "race_title", "title", "race_name", default="")
        ).strip()
        if race_title:
            return race_title

    return str(
        pick(data, "race_title", "title", "race_name", default="")
    ).strip()


def main():
    player_index = []
    seen = set()

    if not RACES_DIR.exists():
        with DST.open("w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        print(f"written: {DST}")
        print("players: 0")
        return

    for path in sorted(RACES_DIR.glob("*.json")):
        try:
            data = load_json(path)
        except Exception:
            continue

        venue_name = extract_venue_name(data)
        if not venue_name:
            continue

        race_no = extract_race_no(data, path)
        if not race_no:
            continue

        jcd = normalize_jcd(pick(data, "jcd", default=""), venue_name)
        race_title = extract_race_title(data)
        day_label = extract_day_label(data)

        boats = extract_boats(data)

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
                "day_label": day_label,
            })

    player_index.sort(
        key=lambda x: (x["name"], x["venue"], x["race"], x["lane"] or 99)
    )

    with DST.open("w", encoding="utf-8") as f:
        json.dump(player_index, f, ensure_ascii=False, indent=2)

    print(f"written: {DST}")
    print(f"players: {len(player_index)}")


if __name__ == "__main__":
    main()