import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RACES_BASE_DIR = ROOT / "data" / "site" / "races"

DST_TODAY = ROOT / "data" / "player_index_today.json"
DST_TOMORROW = ROOT / "data" / "player_index_tomorrow.json"

MERGED_PLAYERS_PATH = ROOT / "data" / "master" / "merged_players.json"

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

JCD_TO_VENUE_NAME = {v: k for k, v in VENUE_NAME_TO_JCD.items()}
KNOWN_VENUE_NAMES = set(VENUE_NAME_TO_JCD.keys())


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
    venue_name = str(venue_name or "").strip()
    return VENUE_NAME_TO_JCD.get(venue_name, "")


def is_valid_venue_name(value):
    return str(value or "").strip() in KNOWN_VENUE_NAMES


def extract_path_hints(path: Path):
    stem = path.stem.strip()
    parts = stem.split("_")
    head = parts[0].strip() if parts else ""

    hinted_jcd = ""
    hinted_venue = ""

    digits = "".join(ch for ch in head if ch.isdigit())
    if digits and digits.zfill(2) in JCD_TO_VENUE_NAME:
        hinted_jcd = digits.zfill(2)
        hinted_venue = JCD_TO_VENUE_NAME[hinted_jcd]
        return hinted_jcd, hinted_venue

    if head in VENUE_NAME_TO_JCD:
        hinted_venue = head
        hinted_jcd = VENUE_NAME_TO_JCD[head]
        return hinted_jcd, hinted_venue

    return "", ""


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
        pick(data, "race_no", "race", "race_number", "number", default="")
    )
    if race_no:
        return race_no

    race_obj = pick(data, "race", default={})
    if isinstance(race_obj, dict):
        race_no = normalize_race_no(
            pick(race_obj, "race_no", "race", "race_number", "number", default="")
        )
        if race_no:
            return race_no

    stem = path.stem
    tail = stem.split("_")[-1]
    return normalize_race_no(tail)


def extract_venue_name(data: dict, path: Path):
    hinted_jcd, hinted_venue = extract_path_hints(path)
    if hinted_venue:
        return hinted_venue

    race_obj = pick(data, "race", default={})
    if isinstance(race_obj, dict):
        for key in ("venue_name", "name", "venue"):
            venue_name = str(pick(race_obj, key, default="")).strip()
            if is_valid_venue_name(venue_name):
                return venue_name

    for key in ("venue_name", "name", "venue"):
        venue_name = str(pick(data, key, default="")).strip()
        if is_valid_venue_name(venue_name):
            return venue_name

    raw_jcd = normalize_jcd(
        pick(data, "jcd", default="") or pick(race_obj, "jcd", default=""),
        ""
    )
    if raw_jcd and raw_jcd in JCD_TO_VENUE_NAME:
        return JCD_TO_VENUE_NAME[raw_jcd]

    if hinted_jcd and hinted_jcd in JCD_TO_VENUE_NAME:
        return JCD_TO_VENUE_NAME[hinted_jcd]

    return ""


def extract_jcd(data: dict, path: Path, venue_name: str):
    hinted_jcd, _ = extract_path_hints(path)
    if hinted_jcd:
        return hinted_jcd

    race_obj = pick(data, "race", default={})
    jcd = normalize_jcd(pick(data, "jcd", default=""), venue_name)
    if jcd:
        return jcd

    if isinstance(race_obj, dict):
        jcd = normalize_jcd(pick(race_obj, "jcd", default=""), venue_name)
        if jcd:
            return jcd

    return normalize_jcd("", venue_name)


def extract_day_label(data: dict):
    race_obj = pick(data, "race", default={})
    if isinstance(race_obj, dict):
        day_label = str(pick(race_obj, "day_label", "day", default="")).strip()
        if day_label:
            return day_label

    return str(pick(data, "day_label", "day", default="")).strip()


def extract_race_title(data: dict):
    race_obj = pick(data, "race", default={})
    if isinstance(race_obj, dict):
        race_title = str(
            pick(race_obj, "race_title", "title", "race_name", default="")
        ).strip()
        if race_title:
            return race_title

    return str(pick(data, "race_title", "title", "race_name", default="")).strip()


def load_merged_players():
    if not MERGED_PLAYERS_PATH.exists():
        return {}
    return load_json(MERGED_PLAYERS_PATH)


def get_date_dirs():
    if not RACES_BASE_DIR.exists():
        return []

    dirs = [p for p in RACES_BASE_DIR.iterdir() if p.is_dir()]
    dirs = [p for p in dirs if p.name[:4].isdigit() and "-" in p.name]
    dirs.sort(key=lambda p: p.name)
    return dirs


def build_player_index(races_dir: Path, merged_players: dict):
    player_index = []
    seen = set()

    if not races_dir.exists():
        return []

    for path in sorted(races_dir.glob("*.json")):
        try:
            data = load_json(path)
        except Exception:
            continue

        venue_name = extract_venue_name(data, path)
        if not venue_name:
            continue

        race_no = extract_race_no(data, path)
        if not race_no:
            continue

        jcd = extract_jcd(data, path, venue_name)
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

            master = merged_players.get(reg_no, {})

            player_index.append({
                "reg_no": reg_no,
                "name": name,
                "venue": venue_name,
                "race": race_no,
                "jcd": jcd,
                "lane": int(lane) if str(lane).isdigit() else "",
                "race_title": race_title,
                "day_label": day_label,
                "avg_st": master.get("avg_st"),
                "st_count": master.get("st_count"),
                "starts": master.get("starts", 0),
                "wins": master.get("wins", 0),
                "top2": master.get("top2", 0),
                "top3": master.get("top3", 0),
                "win_rate": master.get("win_rate", 0),
                "top2_rate": master.get("top2_rate", 0),
                "top3_rate": master.get("top3_rate", 0),
                "course_stats": master.get("course_stats", {})
            })

    player_index.sort(
        key=lambda x: (x["name"], x["venue"], x["race"], x["lane"] or 99)
    )
    return player_index


def write_index(path: Path, rows):
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def main():
    merged_players = load_merged_players()
    date_dirs = get_date_dirs()

    today_rows = []
    tomorrow_rows = []

    if len(date_dirs) >= 1:
        today_rows = build_player_index(date_dirs[0], merged_players)

    if len(date_dirs) >= 2:
        tomorrow_rows = build_player_index(date_dirs[1], merged_players)

    write_index(DST_TODAY, today_rows)
    write_index(DST_TOMORROW, tomorrow_rows)

    print(f"base_dir: {RACES_BASE_DIR}")
    print(f"date_dirs: {[p.name for p in date_dirs]}")
    print(f"written: {DST_TODAY}")
    print(f"players_today: {len(today_rows)}")
    print(f"written: {DST_TOMORROW}")
    print(f"players_tomorrow: {len(tomorrow_rows)}")


if __name__ == "__main__":
    main()