# scripts/build_race_json.py
# data/mbrace_races_YYYY-MM-DD.json
# → data/site/races/YYYY-MM-DD/{jcd}_{rno}R.json
# → data/site/venues/YYYY-MM-DD.json
#
# 方針:
# - 通常運用では mbrace_races_*.json のうち最新1件だけを処理する
# - data/site/races, data/site/venues は全消ししない
# - 最新日だけ更新し、365日より古い site データだけ削除する
# - 前回使用者の支部/年齢は source files(mbrace_races_YYYY-MM-DD.json)を
#   新しい日付から順に見て最初に見つかった最新情報を使う
# - モーター世代切替対応:
#   race_date が会場ごとの reset_date 以降なら、
#   その日以降の履歴だけを現世代として扱う
# - reset当日は強制で is_new_motor = true にする
# - meet_perf は会場ごとに1回だけ読む（レースごと再読込しない）
# - 枠傾向UIの別コース参照用に、各艇へ 1〜6 コース分の
#   waku_recent / waku_recent_local を by_course 形式で積む

import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

SRC_DIR = "data"
OUT_RACES_BASE = "data/site/races"
OUT_VENUES_BASE = "data/site/venues"
MERGED_PLAYERS_PATH = "data/master/merged_players.json"
PLAYER_COURSE_STATS_1Y_PATH = "data/player_course_stats_1y.json"
MEET_PERF_BASE = "data/meet_perf"
FL_MAP_PATH = "data/fl_map.json"
WAKU_RECENT_PATH = "data/waku_recent.json"
WAKU_RECENT_LOCAL_PATH = "data/waku_recent_local.json"
MOTOR_HISTORY_PATH = "data/motor_history.json"
MOTOR_RESET_DATES_PATH = "data/motor_reset_dates.json"

KEEP_DAYS = 365

VENUE_TO_JCD = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}

JCD_TO_VENUE_KEY = {
    "01": "kiryu",
    "02": "toda",
    "03": "edogawa",
    "04": "heiwajima",
    "05": "tamagawa",
    "06": "hamanako",
    "07": "gamagori",
    "08": "tokoname",
    "09": "tsu",
    "10": "mikuni",
    "11": "biwako",
    "12": "suminoe",
    "13": "amagasaki",
    "14": "naruto",
    "15": "marugame",
    "16": "kojima",
    "17": "miyajima",
    "18": "tokuyama",
    "19": "shimonoseki",
    "20": "wakamatsu",
    "21": "ashiya",
    "22": "fukuoka",
    "23": "karatsu",
    "24": "omura",
}

RE_SRC = re.compile(r"^mbrace_races_(\d{4}-\d{2}-\d{2})\.json$")
RE_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_DATE_JSON = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def safe_name(s: str) -> str:
    s = str(s or "").strip().replace(" ", "").replace("　", "")
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    return s


def _write_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as wf:
        json.dump(obj, wf, ensure_ascii=False, indent=2)


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_meet_perf(date_str: str, jcd: str) -> Dict[str, Any]:
    if not date_str or not jcd:
        return {}

    path = os.path.join(MEET_PERF_BASE, f"{date_str}_{jcd}.json")
    if not os.path.exists(path):
        return {}

    try:
        return _load_json(path)
    except Exception:
        return {}


def _normalize_days(raw_days: Any) -> List[List[Any]]:
    out: List[List[Any]] = []

    if not isinstance(raw_days, list):
        return out

    for day in raw_days:
        if not isinstance(day, list):
            out.append([None, None])
            continue

        pair = []
        for i in range(2):
            slot = day[i] if i < len(day) else None
            if isinstance(slot, dict):
                pair.append({
                    "course": slot.get("course"),
                    "st": slot.get("st"),
                    "rank": slot.get("rank"),
                })
            else:
                pair.append(None)
        out.append(pair)

    return out


def _find_meet_perf_for_boat(boat: Dict[str, Any], racers: Dict[str, Any]) -> List[List[Any]]:
    reg_key = _to_reg_key(boat.get("regno"))
    if reg_key and isinstance(racers.get(reg_key), dict):
        return _normalize_days(racers[reg_key].get("days"))

    boat_name = str(boat.get("name") or "").replace(" ", "").replace("　", "").strip()
    if not boat_name:
        return []

    for value in racers.values():
        if not isinstance(value, dict):
            continue
        racer_name = str(value.get("name") or "").replace(" ", "").replace("　", "").strip()
        if racer_name == boat_name:
            return _normalize_days(value.get("days"))

    return []


def _attach_meet_perf_to_race(out: Dict[str, Any], meet_perf_json: Dict[str, Any]) -> Dict[str, Any]:
    race = dict(out.get("race") or {})
    boats = race.get("boats") or []
    racers = meet_perf_json.get("racers") or {}
    day_no = meet_perf_json.get("day_no", 0)

    if not isinstance(boats, list):
        out["race"] = race
        out["meet_day_no"] = day_no
        return out

    new_boats = []
    for boat in boats:
        if not isinstance(boat, dict):
            new_boats.append(boat)
            continue

        b = dict(boat)
        b["meet_perf"] = _find_meet_perf_for_boat(b, racers)
        new_boats.append(b)

    race["boats"] = new_boats
    out["race"] = race
    out["meet_day_no"] = day_no
    return out


def _load_merged_players() -> Dict[str, Any]:
    if not os.path.exists(MERGED_PLAYERS_PATH):
        print(f"warn: merged players not found: {MERGED_PLAYERS_PATH}")
        return {}
    try:
        return _load_json(MERGED_PLAYERS_PATH)
    except Exception as e:
        print(f"warn: failed to load merged players: {e}")
        return {}


def _load_fl_map() -> Dict[str, Any]:
    if not os.path.exists(FL_MAP_PATH):
        return {}
    try:
        with open(FL_MAP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"warn: failed to load fl_map: {e}")
        return {}


def _load_waku_recent() -> Dict[str, Any]:
    if not os.path.exists(WAKU_RECENT_PATH):
        return {}
    try:
        return _load_json(WAKU_RECENT_PATH)
    except Exception as e:
        print(f"warn: failed to load waku_recent: {e}")
        return {}


def _load_waku_recent_local() -> Dict[str, Any]:
    if not os.path.exists(WAKU_RECENT_LOCAL_PATH):
        return {}
    try:
        return _load_json(WAKU_RECENT_LOCAL_PATH)
    except Exception as e:
        print(f"warn: failed to load waku_recent_local: {e}")
        return {}


def _load_motor_history() -> Dict[str, Any]:
    if not os.path.exists(MOTOR_HISTORY_PATH):
        print(f"warn: motor history not found: {MOTOR_HISTORY_PATH}")
        return {}
    try:
        with open(MOTOR_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"warn: failed to load motor_history: {e}")
        return {}


def _load_motor_reset_dates() -> Dict[str, Any]:
    if not os.path.exists(MOTOR_RESET_DATES_PATH):
        print(f"warn: motor reset dates not found: {MOTOR_RESET_DATES_PATH}")
        return {}
    try:
        with open(MOTOR_RESET_DATES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"warn: failed to load motor_reset_dates: {e}")
        return {}


def load_player_course_stats_1y():
    if not os.path.exists(PLAYER_COURSE_STATS_1Y_PATH):
        return {}

    try:
        with open(PLAYER_COURSE_STATS_1Y_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("players", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _to_reg_key(v: Any) -> str:
    s = str(v or "").strip()
    return s if s.isdigit() else ""


def _to_float_or_none(v: Any) -> Any:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _normalize_st_for_output(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""

    try:
        n = float(s)
        return f"{n:.2f}".replace("0.", ".")
    except Exception:
        return s


def _to_motor_key(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    if s.isdigit():
        return str(int(s))
    return s


def _normalize_title(v: Any) -> str:
    return str(v or "").replace(" ", "").replace("　", "").strip()


def _normalize_meet_key(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""

    s = unicodedata.normalize("NFKC", s)
    s = s.replace(" ", "").replace("　", "")
    s = s.replace("〜", "ー").replace("～", "ー")
    s = s.replace("（", "(").replace("）", ")")

    if "_" in s:
        head, tail = s.split("_", 1)
        if head.isdigit():
            head = head.zfill(2)
        s = f"{head}_{tail}"

    return s


def _same_meet_key(a: Any, b: Any) -> bool:
    na = _normalize_meet_key(a)
    nb = _normalize_meet_key(b)
    return bool(na and nb and na == nb)


def _build_meet_key(jcd: str, event_title: str) -> str:
    j = str(jcd or "").zfill(2)
    title = _normalize_title(event_title)
    return _normalize_meet_key(f"{j}_{title}") if j and title else ""


def _build_recent_player_map(src_files: List[str]) -> Dict[str, Dict[str, Any]]:
    recent_map: Dict[str, Dict[str, Any]] = {}

    for src_path in sorted(src_files, reverse=True):
        try:
            data = _load_json(src_path)
        except Exception:
            continue

        venues = data.get("venues") or []
        if not isinstance(venues, list):
            continue

        for venue in venues:
            races = venue.get("races") or []
            if not isinstance(races, list):
                continue

            for race in races:
                boats = race.get("boats") or []
                if not isinstance(boats, list):
                    continue

                for boat in boats:
                    if not isinstance(boat, dict):
                        continue

                    reg_key = _to_reg_key(boat.get("regno"))
                    if not reg_key or reg_key in recent_map:
                        continue

                    recent_map[reg_key] = {
                        "regno": reg_key,
                        "name": str(boat.get("name") or "").strip(),
                        "branch": str(boat.get("branch") or "").strip(),
                        "age": boat.get("age"),
                    }

    return recent_map


def _effective_reset_date(
    race_date: str,
    jcd: str,
    motor_reset_dates: Dict[str, Any],
) -> str:
    target_date = str(race_date or "").strip()
    target_jcd = str(jcd or "").zfill(2)
    venue_key = JCD_TO_VENUE_KEY.get(target_jcd, "")
    reset_date = str(motor_reset_dates.get(venue_key) or "").strip()

    if not target_date or not reset_date:
        return ""

    if target_date < reset_date:
        return ""

    return reset_date


def _empty_motor_prev(motor_key: str, is_new_motor: bool = False, reset_date: str = "") -> Dict[str, Any]:
    return {
        "motor_no": int(motor_key) if motor_key and motor_key.isdigit() else (motor_key or None),
        "prev_date": "",
        "prev_rider": "",
        "prev_rider_name": "",
        "prev_rider_regno": "",
        "prev_rider_branch": "",
        "prev_rider_age": None,
        "records": [],
        "days": [[None, None] for _ in range(7)],
        "day_labels": ["1日目", "2日目", "3日目", "4日目", "5日目", "6日目", "7日目"],
        "avg_st": None,
        "win_rate": None,
        "is_new_motor": is_new_motor,
        "reset_date": reset_date,
    }


def _build_motor_prev(
    boat: Dict[str, Any],
    motor_history: Dict[str, Any],
    motor_reset_dates: Dict[str, Any],
    race_date: str,
    jcd: str,
    current_meet_key: str,
    recent_player_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    motor_key = _to_motor_key(boat.get("motor_no"))
    if not motor_key:
        return _empty_motor_prev(motor_key)

    target_jcd = str(jcd or "").zfill(2)
    history_key = f"{target_jcd}_{motor_key}"

    rows = motor_history.get(history_key)
    rows = rows if isinstance(rows, list) else []

    target_date = str(race_date or "").strip()
    normalized_current_meet_key = _normalize_meet_key(current_meet_key)
    reset_date = _effective_reset_date(target_date, target_jcd, motor_reset_dates)

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        row_date = str(row.get("date") or "").strip()
        if target_date and row_date >= target_date:
            continue

        row_jcd = str(row.get("jcd") or "").zfill(2)
        if target_jcd and row_jcd and row_jcd != target_jcd:
            continue

        row_meet_key = str(row.get("meet_key") or "").strip()

        if normalized_current_meet_key and _same_meet_key(row_meet_key, normalized_current_meet_key):
            continue

        if reset_date and row_date and row_date < reset_date:
            continue

        filtered.append(row)

    is_new_motor = False
    if reset_date:
        if target_date == reset_date:
            is_new_motor = True
        elif len(filtered) == 0:
            is_new_motor = True

    if is_new_motor:
        return _empty_motor_prev(motor_key, is_new_motor=True, reset_date=reset_date)

    if not filtered:
        return _empty_motor_prev(motor_key, is_new_motor=False, reset_date=reset_date)

    filtered.sort(
        key=lambda x: (
            str(x.get("date") or ""),
            int(x.get("rno") or 0),
        ),
        reverse=True,
    )

    latest_prev = filtered[0]
    prev_meet_key = str(latest_prev.get("meet_key") or "").strip()
    normalized_prev_meet_key = _normalize_meet_key(prev_meet_key)

    if normalized_prev_meet_key:
        prev_segment = [
            row for row in filtered
            if _same_meet_key(str(row.get("meet_key") or "").strip(), normalized_prev_meet_key)
        ]
    else:
        fallback_date = str(latest_prev.get("date") or "").strip()
        prev_segment = [row for row in filtered if str(row.get("date") or "").strip() == fallback_date]

    if not prev_segment:
        return _empty_motor_prev(motor_key, is_new_motor=False, reset_date=reset_date)

    prev_segment.sort(
        key=lambda x: (
            str(x.get("date") or ""),
            int(x.get("rno") or 0),
        )
    )

    unique_dates = sorted({
        str(r.get("date") or "").strip()
        for r in prev_segment
        if str(r.get("date") or "").strip()
    })

    date_to_day_index = {d: i for i, d in enumerate(unique_dates[:7])}

    days: List[List[Any]] = [[None, None] for _ in range(7)]
    normalized_records: List[Dict[str, Any]] = []
    st_vals: List[float] = []
    finish_nums: List[int] = []

    prev_date = unique_dates[-1] if unique_dates else ""
    prev_name = str(latest_prev.get("name") or "").strip()
    prev_regno = str(latest_prev.get("regno") or latest_prev.get("reg") or "").strip()

    prev_player = recent_player_map.get(prev_regno, {}) if prev_regno else {}
    prev_branch = str(prev_player.get("branch") or "").strip()
    prev_age = prev_player.get("age")

    day_grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for r in prev_segment:
        row_date = str(r.get("date") or "").strip()
        if row_date not in date_to_day_index:
            continue

        finish = r.get("finish")
        st_raw = r.get("st_raw", r.get("st", ""))
        waku = r.get("boat")
        course = r.get("course", r.get("boat"))

        slot = {
            "race": r.get("rno"),
            "waku": waku,
            "finish": finish,
            "st": _normalize_st_for_output(st_raw),
            "course": course,
            "rank": finish,
        }

        day_grouped[row_date].append(slot)
        normalized_records.append(slot)

        st_num = _to_float_or_none(st_raw)
        if st_num is not None:
            st_vals.append(st_num)

        try:
            finish_int = int(finish)
            finish_nums.append(finish_int)
        except Exception:
            pass

    for date_key, items in day_grouped.items():
        items.sort(key=lambda x: int(x.get("race") or 0))
        day_index = date_to_day_index[date_key]

        pair: List[Any] = [None, None]
        if len(items) >= 1:
            pair[0] = items[0]
        if len(items) >= 2:
            pair[1] = items[1]

        days[day_index] = pair

    avg_st = round(sum(st_vals) / len(st_vals), 2) if st_vals else None
    win_rate = round(sum(1 for x in finish_nums if x == 1) / len(finish_nums) * 100, 2) if finish_nums else None

    return {
        "motor_no": int(motor_key) if motor_key.isdigit() else motor_key,
        "prev_date": prev_date,
        "prev_rider": prev_name,
        "prev_rider_name": prev_name,
        "prev_rider_regno": prev_regno,
        "prev_rider_branch": prev_branch,
        "prev_rider_age": prev_age,
        "records": normalized_records,
        "days": days,
        "day_labels": ["1日目", "2日目", "3日目", "4日目", "5日目", "6日目", "7日目"],
        "avg_st": avg_st,
        "win_rate": win_rate,
        "is_new_motor": is_new_motor,
        "reset_date": reset_date,
    }


def _build_recent_course_bundle(
    reg_key: str,
    jcd: str,
    recent_map: Dict[str, Any],
    is_local: bool = False,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    records_by_course: Dict[str, List[Dict[str, Any]]] = {}
    avg_st_by_course: Dict[str, Any] = {}

    target_jcd = str(jcd or "").zfill(2)

    for course_no in range(1, 7):
        course_key = str(course_no)

        if is_local:
            key = f"{reg_key}_{course_key}_{target_jcd}"
        else:
            key = f"{reg_key}_{course_key}"

        row = recent_map.get(key)
        if isinstance(row, dict):
            records = row.get("records", [])
            avg_st = row.get("avg_st")
            records_by_course[course_key] = records if isinstance(records, list) else []
            avg_st_by_course[course_key] = avg_st
        else:
            records_by_course[course_key] = []
            avg_st_by_course[course_key] = None

    return records_by_course, avg_st_by_course


def _merge_boat_stats(
    boat: Dict[str, Any],
    merged_players: Dict[str, Any],
    player_course_stats_1y,
    waku_recent_map,
    waku_recent_local_map,
    jcd: str,
):
    out = dict(boat)
    reg_key = _to_reg_key(out.get("regno"))

    if not reg_key:
        out["waku_recent_by_course"] = {str(i): [] for i in range(1, 7)}
        out["waku_recent_avg_st_by_course"] = {str(i): None for i in range(1, 7)}
        out["waku_recent_local_by_course"] = {str(i): [] for i in range(1, 7)}
        out["waku_recent_local_avg_st_by_course"] = {str(i): None for i in range(1, 7)}
        out["waku_recent"] = []
        out["waku_recent_avg_st"] = None
        out["waku_recent_local"] = []
        out["waku_recent_local_avg_st"] = None
        return out

    mp = merged_players.get(reg_key)
    mp = mp if isinstance(mp, dict) else {}

    master_name = str(mp.get("name") or "").strip()
    if master_name:
        out["name"] = master_name

    players_1y = player_course_stats_1y if isinstance(player_course_stats_1y, dict) else {}
    p = players_1y.get(reg_key, {})
    p = p if isinstance(p, dict) else {}

    st_count = mp.get("st_count")
    player_avg_st = p.get("avg_st")

    if player_avg_st is None:
        player_avg_st = mp.get("avg_st")

    if player_avg_st is None:
        player_avg_st = mp.get("st")

    if player_avg_st is not None:
        out["avg_st"] = player_avg_st

    if st_count is not None:
        out["st_count"] = st_count

    course_key = str(int(out.get("waku"))) if out.get("waku") else ""
    courses = p.get("courses", {}) if isinstance(p, dict) else {}
    courses = courses if isinstance(courses, dict) else {}

    course = (
        courses.get(course_key)
        or courses.get(str(out.get("waku")))
        or {}
    )
    course = course if isinstance(course, dict) else {}

    kimarite = course.get("kimarite", {}) if isinstance(course, dict) else {}
    kimarite = kimarite if isinstance(kimarite, dict) else {}

    out["course_starts"] = course.get("starts")
    out["course_win"] = course.get("win_rate")
    out["course_2ren"] = course.get("ren2_rate")
    out["course_3ren"] = course.get("ren3_rate")
    out["course_avg_st"] = course.get("avg_st")
    out["course_sashi"] = kimarite.get("差し", 0)
    out["course_makuri"] = kimarite.get("まくり", 0)
    out["course_makurisashi"] = kimarite.get("まくり差し", 0)

    waku = str(out.get("waku") or "").strip()

    wr_by_course, wr_avg_by_course = _build_recent_course_bundle(
        reg_key,
        jcd,
        waku_recent_map,
        is_local=False,
    )
    out["waku_recent_by_course"] = wr_by_course
    out["waku_recent_avg_st_by_course"] = wr_avg_by_course

    wr_local_by_course, wr_local_avg_by_course = _build_recent_course_bundle(
        reg_key,
        jcd,
        waku_recent_local_map,
        is_local=True,
    )
    out["waku_recent_local_by_course"] = wr_local_by_course
    out["waku_recent_local_avg_st_by_course"] = wr_local_avg_by_course

    key = f"{reg_key}_{waku}"
    wr = waku_recent_map.get(key)
    if isinstance(wr, dict):
        records = wr.get("records", [])
        out["waku_recent"] = records if isinstance(records, list) else []
        out["waku_recent_avg_st"] = wr.get("avg_st")
    else:
        out["waku_recent"] = []
        out["waku_recent_avg_st"] = None

    local_key = f"{reg_key}_{waku}_{str(jcd or '').zfill(2)}"
    wr_local = waku_recent_local_map.get(local_key)
    if isinstance(wr_local, dict):
        records = wr_local.get("records", [])
        out["waku_recent_local"] = records if isinstance(records, list) else []
        out["waku_recent_local_avg_st"] = wr_local.get("avg_st")
    else:
        out["waku_recent_local"] = []
        out["waku_recent_local_avg_st"] = None

    return out


def _merge_race_stats(
    race,
    merged_players,
    player_course_stats_1y,
    waku_recent_map,
    waku_recent_local_map,
    jcd: str,
):
    out = dict(race)
    boats = out.get("boats") or []
    if not isinstance(boats, list):
        out["boats"] = []
        return out

    out["boats"] = [
        _merge_boat_stats(
            b,
            merged_players,
            player_course_stats_1y,
            waku_recent_map,
            waku_recent_local_map,
            jcd,
        ) if isinstance(b, dict) else b
        for b in boats
    ]
    return out


def _attach_fl_to_race(race: Dict[str, Any], fl_map: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(race)
    boats = out.get("boats") or []

    if not isinstance(boats, list):
        out["boats"] = []
        return out

    new_boats = []
    for boat in boats:
        if not isinstance(boat, dict):
            new_boats.append(boat)
            continue

        b = dict(boat)
        regno = str(int(b.get("regno") or 0))
        fl = fl_map.get(regno, {}) if regno else {}

        b["F"] = fl.get("F", 0)
        b["L"] = fl.get("L", 0)

        new_boats.append(b)

    out["boats"] = new_boats
    return out


def _attach_motor_prev_to_race(
    race: Dict[str, Any],
    motor_history: Dict[str, Any],
    motor_reset_dates: Dict[str, Any],
    race_date: str,
    jcd: str,
    current_meet_key: str,
    recent_player_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    out = dict(race)
    boats = out.get("boats") or []

    if not isinstance(boats, list):
        out["boats"] = []
        return out

    new_boats = []
    for boat in boats:
        if not isinstance(boat, dict):
            new_boats.append(boat)
            continue

        b = dict(boat)
        motor_prev = _build_motor_prev(
            b,
            motor_history,
            motor_reset_dates,
            race_date,
            jcd,
            current_meet_key,
            recent_player_map,
        )
        b["motor_prev"] = motor_prev
        b["is_new_motor"] = bool(motor_prev.get("is_new_motor"))
        new_boats.append(b)

    out["boats"] = new_boats
    return out


def _collect_sources() -> List[str]:
    if not os.path.isdir(SRC_DIR):
        return []

    files: List[str] = []
    for name in os.listdir(SRC_DIR):
        if RE_SRC.match(name):
            files.append(os.path.join(SRC_DIR, name))

    files.sort()
    return files


def _collect_latest_source(src_files: List[str]) -> List[str]:
    return src_files[-1:] if src_files else []


def _clear_day_outputs(date_str: str) -> None:
    race_dir = os.path.join(OUT_RACES_BASE, date_str)
    if os.path.isdir(race_dir):
        for root, dirs, files in os.walk(race_dir, topdown=False):
            for fn in files:
                try:
                    os.remove(os.path.join(root, fn))
                except Exception:
                    pass
            for dn in dirs:
                try:
                    os.rmdir(os.path.join(root, dn))
                except Exception:
                    pass
        try:
            os.rmdir(race_dir)
        except Exception:
            pass

    venue_path = os.path.join(OUT_VENUES_BASE, f"{date_str}.json")
    if os.path.exists(venue_path):
        try:
            os.remove(venue_path)
        except Exception:
            pass


def _cleanup_old_site_outputs(keep_days: int = KEEP_DAYS) -> None:
    today = datetime.now().date()
    limit_date = today - timedelta(days=keep_days)

    if os.path.isdir(OUT_RACES_BASE):
        for name in os.listdir(OUT_RACES_BASE):
            if not RE_DATE_DIR.match(name):
                continue
            try:
                d = datetime.strptime(name, "%Y-%m-%d").date()
            except Exception:
                continue
            if d < limit_date:
                path = os.path.join(OUT_RACES_BASE, name)
                for root, dirs, files in os.walk(path, topdown=False):
                    for fn in files:
                        try:
                            os.remove(os.path.join(root, fn))
                        except Exception:
                            pass
                    for dn in dirs:
                        try:
                            os.rmdir(os.path.join(root, dn))
                        except Exception:
                            pass
                try:
                    os.rmdir(path)
                except Exception:
                    pass

    if os.path.isdir(OUT_VENUES_BASE):
        for name in os.listdir(OUT_VENUES_BASE):
            m = RE_DATE_JSON.match(name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except Exception:
                continue
            if d < limit_date:
                path = os.path.join(OUT_VENUES_BASE, name)
                try:
                    os.remove(path)
                except Exception:
                    pass


def _build_race_times(races: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for race in races:
        try:
            rno = int(race.get("rno"))
        except Exception:
            continue

        cutoff = str(race.get("cutoff") or "").strip()
        if not cutoff:
            continue

        out.append({
            "rno": rno,
            "cutoff": cutoff,
        })

    out.sort(key=lambda x: x["rno"])
    return out


def _build_venue_card(v: Dict[str, Any], top_date: str) -> Dict[str, Any]:
    venue_name = str(v.get("venue") or "").strip()
    date = str(v.get("date") or top_date).strip()
    day = v.get("day")
    total_days = v.get("total_days")
    day_label = v.get("day_label")
    event_title = v.get("event_title") or ""
    grade_label = v.get("grade_label") or ""
    races = v.get("races") or []

    jcd = VENUE_TO_JCD.get(venue_name, "") or "00"

    return {
        "jcd": jcd,
        "name": venue_name,
        "venue_name": venue_name,
        "date": date,
        "day": day,
        "total_days": total_days,
        "day_label": day_label,
        "event_title": event_title,
        "grade_label": grade_label,
        "race_times": _build_race_times(races),
    }


def build_one(
    src_path: str,
    merged_players: Dict[str, Any],
    player_course_stats_1y,
    fl_map,
    waku_recent_map,
    waku_recent_local_map,
    motor_history,
    motor_reset_dates,
    recent_player_map,
):
    if not os.path.exists(src_path):
        print(f"skip: {src_path} not found")
        return 0, 0, 0

    data = _load_json(src_path)
    top_date = str(data.get("date") or "").strip()

    if not top_date:
        print(f"skip: no top date in {src_path}")
        return 0, 0, 0

    _clear_day_outputs(top_date)

    out_race_dir = os.path.join(OUT_RACES_BASE, top_date)
    os.makedirs(out_race_dir, exist_ok=True)
    os.makedirs(OUT_VENUES_BASE, exist_ok=True)

    venues: List[Dict[str, Any]] = data.get("venues") or []
    created = 0
    skipped = 0
    venue_cards: List[Dict[str, Any]] = []

    for v in venues:
        venue_name = str(v.get("venue") or "").strip()
        date = str(v.get("date") or top_date).strip()
        day = v.get("day")
        total_days = v.get("total_days")
        day_label = v.get("day_label")
        event_title = v.get("event_title") or ""
        grade_label = v.get("grade_label") or ""
        races = v.get("races") or []

        jcd = VENUE_TO_JCD.get(venue_name, "") or "00"
        current_meet_key = _build_meet_key(jcd, event_title)

        venue_cards.append(_build_venue_card(v, top_date))

        meet_perf_json = _load_meet_perf(date, jcd) if jcd != "00" else {}

        for race in races:
            rno = race.get("rno")
            try:
                rno_i = int(rno)
            except Exception:
                skipped += 1
                continue

            merged_race = _merge_race_stats(
                race,
                merged_players,
                player_course_stats_1y,
                waku_recent_map,
                waku_recent_local_map,
                jcd,
            )

            merged_race = _attach_fl_to_race(merged_race, fl_map)
            merged_race = _attach_motor_prev_to_race(
                merged_race,
                motor_history,
                motor_reset_dates,
                date,
                jcd,
                current_meet_key,
                recent_player_map,
            )

            out: Dict[str, Any] = {
                "date": date,
                "venue": venue_name,
                "jcd": jcd if jcd != "00" else None,
                "day": day,
                "total_days": total_days,
                "day_label": day_label,
                "event_title": event_title,
                "grade_label": grade_label,
                "race": merged_race,
            }

            out = _attach_meet_perf_to_race(out, meet_perf_json)

            stable_fname = f"{jcd}_{rno_i}R.json"
            stable_path = os.path.join(out_race_dir, stable_fname)
            _write_json(stable_path, out)
            created += 1

            legacy_fname = f"{safe_name(venue_name)}_{rno_i}R.json"
            legacy_path = os.path.join(out_race_dir, legacy_fname)
            if legacy_path != stable_path:
                _write_json(legacy_path, out)

    venue_count = len(venue_cards)

    venues_payload: Dict[str, Any] = {
        "date": top_date,
        "venue_count": venue_count,
        "venues": venue_cards,
    }
    venues_out_path = os.path.join(OUT_VENUES_BASE, f"{top_date}.json")
    _write_json(venues_out_path, venues_payload)

    print(f"source: {src_path}")
    print(f"date: {top_date}")
    print(f"created_races: {created}")
    print(f"created_venues: {venue_count}")
    if skipped:
        print(f"skipped: {skipped}")

    return created, skipped, venue_count


def main():
    total_created = 0
    total_skipped = 0
    total_venues = 0

    merged_players = _load_merged_players()
    player_course_stats_1y = load_player_course_stats_1y()
    fl_map = _load_fl_map()
    waku_recent_map = _load_waku_recent()
    waku_recent_local_map = _load_waku_recent_local()
    motor_history = _load_motor_history()
    motor_reset_dates = _load_motor_reset_dates()

    print("merged_players:", len(merged_players))
    print("fl_map:", len(fl_map))
    print("waku_recent:", len(waku_recent_map))
    print("waku_recent_local:", len(waku_recent_local_map))
    print("motor_history:", len(motor_history))
    print("motor_reset_dates:", len(motor_reset_dates))

    src_files = _collect_sources()
    print("source_files:", len(src_files))

    recent_player_map = _build_recent_player_map(src_files)
    print("recent_player_map:", len(recent_player_map))

    target_files = _collect_latest_source(src_files)
    print("target_files:", len(target_files))
    if target_files:
        print("target_source:", target_files[0])

    for src_path in target_files:
        created, skipped, venues_created = build_one(
            src_path,
            merged_players,
            player_course_stats_1y,
            fl_map,
            waku_recent_map,
            waku_recent_local_map,
            motor_history,
            motor_reset_dates,
            recent_player_map,
        )
        total_created += created
        total_skipped += skipped
        total_venues += venues_created

    _cleanup_old_site_outputs(KEEP_DAYS)

    print("done")
    print("total_created_races:", total_created)
    print("total_created_venues:", total_venues)
    if total_skipped:
        print("total_skipped:", total_skipped)


if __name__ == "__main__":
    main()