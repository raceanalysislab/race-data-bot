import json
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]

SRC_RESULTS = ROOT / "data" / "k_results_parsed.json"
OUT_STATS = ROOT / "data" / "master" / "advanced_player_stats.json"

LOOKBACK_DAYS = 365 * 3

VALID_KIMARITE = {
    "逃げ",
    "差し",
    "まくり",
    "まくり差し",
    "抜き",
    "恵まれ",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def empty_rate_box():
    return {
        "starts": 0,
        "wins": 0,
        "top2": 0,
        "top3": 0,
        "win_rate": 0.0,
        "top2_rate": 0.0,
        "top3_rate": 0.0,
    }


def empty_course_box():
    box = empty_rate_box()
    box["kimarite_wins"] = {}
    return box


def ensure_player(players: dict, reg: str, name: str):
    if reg not in players:
        players[reg] = {
            "reg": reg,
            "name": name,
            "local_stats": {},
            "course_stats": {},
            "course_rival_stats": {},
            "course_win_styles": {},
        }
    elif name and not players[reg].get("name"):
        players[reg]["name"] = name
    return players[reg]


def ensure_local_box(player: dict, venue: str):
    if venue not in player["local_stats"]:
        player["local_stats"][venue] = empty_rate_box()
    return player["local_stats"][venue]


def ensure_course_box(player: dict, course: str):
    if course not in player["course_stats"]:
        player["course_stats"][course] = empty_course_box()
    return player["course_stats"][course]


def ensure_course_win_style_box(player: dict, course: str):
    if course not in player["course_win_styles"]:
        player["course_win_styles"][course] = {
            "wins": 0,
            "kimarite_wins": {}
        }
    return player["course_win_styles"][course]


def ensure_rival_box(player: dict, own_course: str, rival_course: str):
    if own_course not in player["course_rival_stats"]:
        player["course_rival_stats"][own_course] = {}
    if rival_course not in player["course_rival_stats"][own_course]:
        box = empty_rate_box()
        box["kimarite_wins"] = {}
        player["course_rival_stats"][own_course][rival_course] = box
    return player["course_rival_stats"][own_course][rival_course]


def add_kimarite(counter_box: dict, kimarite: str):
    if not kimarite:
        return
    if "kimarite_wins" not in counter_box:
        counter_box["kimarite_wins"] = {}
    counter_box["kimarite_wins"][kimarite] = counter_box["kimarite_wins"].get(kimarite, 0) + 1


def finalize_rate_box(box: dict):
    starts = safe_int(box.get("starts", 0))
    wins = safe_int(box.get("wins", 0))
    top2 = safe_int(box.get("top2", 0))
    top3 = safe_int(box.get("top3", 0))

    if starts > 0:
        box["win_rate"] = round(wins / starts * 100, 2)
        box["top2_rate"] = round(top2 / starts * 100, 2)
        box["top3_rate"] = round(top3 / starts * 100, 2)
    else:
        box["win_rate"] = 0.0
        box["top2_rate"] = 0.0
        box["top3_rate"] = 0.0


def finalize_all(players: dict):
    for player in players.values():
        for venue_box in player["local_stats"].values():
            finalize_rate_box(venue_box)

        for course_box in player["course_stats"].values():
            finalize_rate_box(course_box)

        for rivals in player["course_rival_stats"].values():
            for rival_box in rivals.values():
                finalize_rate_box(rival_box)


def normalize_kimarite(label: str):
    s = str(label or "").strip()
    if s in VALID_KIMARITE:
        return s
    return ""


def normalize_finish(v):
    if isinstance(v, int):
        return v
    s = str(v or "").strip()
    if s.isdigit():
        return int(s)
    return s


def normalize_course(v):
    s = str(v or "").strip()
    if s.isdigit() and 1 <= int(s) <= 6:
        return str(int(s))
    return ""


def extract_kimarite_from_race(race: dict):
    label = str(race.get("label", "")).strip()
    return normalize_kimarite(label)


def main():
    if not SRC_RESULTS.exists():
        print(f"missing: {SRC_RESULTS}")
        return

    payload = load_json(SRC_RESULTS)
    venues = payload.get("venues", [])

    today = datetime.now().date()
    cutoff = today - timedelta(days=LOOKBACK_DAYS)

    players = {}
    used_venues = 0
    used_races = 0

    for venue_block in venues:
        venue = str(venue_block.get("venue", "")).strip()
        date_str = str(venue_block.get("date", "")).strip()
        races = venue_block.get("races", [])

        race_date = parse_date(date_str)
        if not venue or not race_date:
            continue

        if race_date < cutoff:
            continue

        used_venues += 1

        for race in races:
            results = race.get("results", [])
            if not results:
                continue

            used_races += 1
            kimarite = extract_kimarite_from_race(race)

            normalized_results = []
            winner = None

            for row in results:
                reg = str(row.get("reg", "")).strip()
                name = str(row.get("name", "")).strip()
                finish = normalize_finish(row.get("finish"))
                course = normalize_course(row.get("course") or row.get("boat"))

                if not reg or not course:
                    continue

                item = {
                    "reg": reg,
                    "name": name,
                    "finish": finish,
                    "course": course,
                }
                normalized_results.append(item)

                if finish == 1:
                    winner = item

            if not normalized_results:
                continue

            for row in normalized_results:
                reg = row["reg"]
                name = row["name"]
                finish = row["finish"]
                course = row["course"]

                player = ensure_player(players, reg, name)

                local_box = ensure_local_box(player, venue)
                local_box["starts"] += 1
                if finish == 1:
                    local_box["wins"] += 1
                if finish in (1, 2):
                    local_box["top2"] += 1
                if finish in (1, 2, 3):
                    local_box["top3"] += 1

                course_box = ensure_course_box(player, course)
                course_box["starts"] += 1
                if finish == 1:
                    course_box["wins"] += 1
                    if kimarite:
                        add_kimarite(course_box, kimarite)
                if finish in (1, 2):
                    course_box["top2"] += 1
                if finish in (1, 2, 3):
                    course_box["top3"] += 1

                if finish == 1:
                    style_box = ensure_course_win_style_box(player, course)
                    style_box["wins"] += 1
                    if kimarite:
                        add_kimarite(style_box, kimarite)

            for base in normalized_results:
                base_reg = base["reg"]
                base_name = base["name"]
                own_course = base["course"]

                player = ensure_player(players, base_reg, base_name)

                for rival in normalized_results:
                    if rival["reg"] == base_reg:
                        continue

                    rival_course = rival["course"]
                    rival_finish = rival["finish"]

                    rival_box = ensure_rival_box(player, own_course, rival_course)
                    rival_box["starts"] += 1

                    if rival_finish == 1:
                        rival_box["wins"] += 1
                        if winner and winner["reg"] == rival["reg"] and kimarite:
                            add_kimarite(rival_box, kimarite)

                    if rival_finish in (1, 2):
                        rival_box["top2"] += 1

                    if rival_finish in (1, 2, 3):
                        rival_box["top3"] += 1

    finalize_all(players)

    OUT_STATS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_STATS.open("w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    print(f"source: {SRC_RESULTS}")
    print(f"out: {OUT_STATS}")
    print(f"players: {len(players)}")
    print(f"used_venues: {used_venues}")
    print(f"used_races: {used_races}")
    print(f"cutoff: {cutoff.isoformat()}")


if __name__ == "__main__":
    main()