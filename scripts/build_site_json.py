import json
import os
import re
import glob
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))


def _extract_date_from_filename(path: str) -> Optional[str]:
    name = os.path.basename(path)
    m = re.match(r"^mbrace_races_(\d{4}-\d{2}-\d{2})\.json$", name)
    if not m:
        return None
    return m.group(1)


def _resolve_src_specs():
    files = sorted(glob.glob("data/mbrace_races_*.json"))
    date_to_path: Dict[str, str] = {}

    for path in files:
        date_str = _extract_date_from_filename(path)
        if date_str:
            date_to_path[date_str] = path

    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now(JST) + timedelta(days=1)).strftime("%Y-%m-%d")

    specs = []

    if today_str in date_to_path:
        specs.append((date_to_path[today_str], "today"))
    else:
        dated = sorted(date_to_path.items(), key=lambda x: x[0])
        if dated:
            specs.append((dated[-1][1], "today"))

    if tomorrow_str in date_to_path:
        specs.append((date_to_path[tomorrow_str], "tomorrow"))

    return specs


SRC_SPECS = _resolve_src_specs()

OUT_DIR = "data/site"
OUT_VENUES_TODAY = os.path.join(OUT_DIR, "venues_today.json")
OUT_VENUES_TOMORROW = os.path.join(OUT_DIR, "venues_tomorrow.json")
OUT_VENUES_COMPAT = os.path.join(OUT_DIR, "venues.json")

OUT_VENUE_DIR = os.path.join(OUT_DIR, "venues")
OUT_VENUE_DIR_TODAY = os.path.join(OUT_VENUE_DIR, "today")
OUT_VENUE_DIR_TOMORROW = os.path.join(OUT_VENUE_DIR, "tomorrow")

os.makedirs(OUT_VENUE_DIR_TODAY, exist_ok=True)
os.makedirs(OUT_VENUE_DIR_TOMORROW, exist_ok=True)

VENUE_TO_JCD: Dict[str, str] = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}


def _pad2(n: int) -> str:
    return str(n).zfill(2)


def _parse_hhmm(hhmm: str) -> Optional[Tuple[int, int]]:
    if not isinstance(hhmm, str):
        return None

    s = hhmm.strip()
    if ":" not in s:
        return None

    try:
        hh, mm = s.split(":")
        h = int(hh)
        m = int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:
        return None

    return None


def _minutes(h: int, m: int) -> int:
    return h * 60 + m


def _to_hhmm(value: Any) -> Optional[str]:
    hm = _parse_hhmm(str(value or ""))
    if not hm:
        return None
    return f"{_pad2(hm[0])}:{_pad2(hm[1])}"


def _normalize_text(value: Any) -> str:
    return str(value or "").replace(" ", "").replace("　", "").strip()


def _normalize_grade_label(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return "一般"

    s = (
        s.replace("Ｇ", "G")
         .replace("Ⅰ", "I")
         .replace("Ⅱ", "II")
         .replace("Ⅲ", "III")
         .upper()
    )

    if s == "SG":
        return "SG"
    if s in {"G1", "GI", "PG1", "PGI"}:
        return "G1"
    if s in {"G2", "GII"}:
        return "G2"
    if s in {"G3", "GIII"}:
        return "G3"
    if s in {"一般", "一般戦"}:
        return "一般"

    return "一般"


def _build_race_times(races: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []

    for r in races:
        rno = r.get("rno")
        cutoff = _to_hhmm(r.get("cutoff"))

        if rno and cutoff:
            out.append({
                "rno": int(rno),
                "cutoff": cutoff
            })

    out.sort(key=lambda x: x["rno"])
    return out


def _detect_first_race_time(races: List[Dict[str, Any]]) -> Optional[str]:
    times = []

    for r in races:
        cutoff = _to_hhmm(r.get("cutoff"))
        if cutoff:
            times.append(cutoff)

    if not times:
        return None

    times.sort()
    return times[0]


def _detect_card_band(first_time: Optional[str]) -> Tuple[str, str]:
    if not first_time:
        return "normal", "normal"

    hm = _parse_hhmm(first_time)
    if not hm:
        return "normal", "normal"

    mins = _minutes(*hm)

    if _minutes(8, 0) <= mins <= _minutes(9, 59):
        return "morning", "morning"

    if _minutes(10, 0) <= mins <= _minutes(12, 59):
        return "day", "day"

    if _minutes(15, 0) <= mins <= _minutes(16, 59):
        return "evening", "evening"

    if _minutes(17, 0) <= mins <= _minutes(18, 59):
        return "night", "night"

    return "normal", "normal"


def _detect_next_race(races: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
    now = datetime.now(JST)
    now_min = _minutes(now.hour, now.minute)

    for r in races:
        cutoff = _to_hhmm(r.get("cutoff"))
        if not cutoff:
            continue

        hm = _parse_hhmm(cutoff)
        if not hm:
            continue

        mins = _minutes(*hm)

        if mins >= now_min:
            return r["rno"], f'{r["rno"]}R {cutoff}'

    return None, None


def _build_venue_entry(venue: Dict[str, Any], slot: str) -> Dict[str, Any]:
    name = venue.get("venue")
    races = venue.get("races", [])

    race_times = _build_race_times(races)
    first_race_time = _detect_first_race_time(races)

    card_band, card_tone = _detect_card_band(first_race_time)
    next_race, next_display = _detect_next_race(race_times)

    entry = {
        "slot": slot,
        "date": venue.get("date"),
        "name": name,
        "jcd": VENUE_TO_JCD.get(name),
        "next_race": next_race,
        "next_display": next_display,
        "day": venue.get("day"),
        "total_days": venue.get("total_days"),
        "day_label": venue.get("day_label"),
        "grade_label": _normalize_grade_label(venue.get("grade_label")),
        "event_title": venue.get("event_title"),
        "first_race_time": first_race_time,
        "card_band": card_band,
        "card_tone": card_tone,
        "race_times": race_times
    }

    return entry


def _write_json(path: str, data: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    venues_today = []
    venues_tomorrow = []

    for path, slot in SRC_SPECS:
        if not os.path.exists(path):
            continue

        with open(path, "r", encoding="utf-8") as f:
            src = json.load(f)

        venues = src.get("venues", [])

        for v in venues:
            entry = _build_venue_entry(v, slot)

            if slot == "today":
                venues_today.append(entry)

                jcd = entry.get("jcd")
                if jcd:
                    out_path = os.path.join(
                        OUT_VENUE_DIR_TODAY,
                        f"{jcd}.json"
                    )
                    _write_json(out_path, entry)

            elif slot == "tomorrow":
                venues_tomorrow.append(entry)

                jcd = entry.get("jcd")
                if jcd:
                    out_path = os.path.join(
                        OUT_VENUE_DIR_TOMORROW,
                        f"{jcd}.json"
                    )
                    _write_json(out_path, entry)

    _write_json(OUT_VENUES_TODAY, venues_today)
    _write_json(OUT_VENUES_TOMORROW, venues_tomorrow)
    _write_json(OUT_VENUES_COMPAT, venues_today if venues_today else venues_tomorrow)

    print("venues_today:", len(venues_today))
    print("venues_tomorrow:", len(venues_tomorrow))


if __name__ == "__main__":
    main()