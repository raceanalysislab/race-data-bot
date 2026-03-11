# scripts/build_site_json.py
# mbrace_races_today.json / mbrace_races_tomorrow.json を正として site 用 JSON を生成する
#
# 出力:
# - data/site/venues_today.json
# - data/site/venues_tomorrow.json
# - data/site/venues/today/<会場>.json
# - data/site/venues/tomorrow/<会場>.json
#
# 互換:
# - data/site/venues.json には today を優先、なければ tomorrow を出す
# - data/site/venues/<会場>.json には today を優先、なければ tomorrow を出す
#
# 追加:
# - grade_label
# - first_race_time
# - card_band
# - card_tone
# - race_times
#
# 追加仕様:
# - 本当の優勝戦のときだけ day_label を「最終日」に上書き
# - 準優勝戦 / 紹介 / インタビュー / トライアル等は除外

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

SRC_SPECS = [
    ("data/mbrace_races_today.json", "today"),
    ("data/mbrace_races_tomorrow.json", "tomorrow"),
]

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


def _to_hhmm(value: str) -> Optional[str]:
    hm = _parse_hhmm(value)
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
    out: List[Dict[str, Any]] = []

    for r in races:
        rno = r.get("rno")
        if not isinstance(rno, int):
            continue

        hhmm = _to_hhmm(str(r.get("cutoff") or ""))
        if not hhmm:
            continue

        out.append({
            "rno": rno,
            "cutoff": hhmm,
        })

    out.sort(key=lambda x: x["rno"])
    return out


def compute_next_from_race_times(race_times: List[Dict[str, Any]]) -> Tuple[Optional[int], str]:
    now = datetime.now(JST)
    now_min = _minutes(now.hour, now.minute)

    candidates: List[Tuple[int, int, str]] = []
    for r in race_times:
        rno = r.get("rno")
        cutoff = r.get("cutoff")

        if not isinstance(rno, int):
            continue

        hhmm = _to_hhmm(str(cutoff or ""))
        if not hhmm:
            continue

        hm = _parse_hhmm(hhmm)
        if not hm:
            continue

        tmin = _minutes(hm[0], hm[1])
        candidates.append((tmin, rno, hhmm))

    if not candidates:
        return None, "発売終了"

    candidates.sort(key=lambda x: x[0])

    for tmin, rno, hhmm in candidates:
        if tmin > now_min:
            return rno, f"{rno}R {hhmm}"

    return None, "発売終了"


def _pick_first_race_time(race_times: List[Dict[str, Any]]) -> Optional[str]:
    for r in race_times:
        if r.get("rno") == 1:
            hhmm = _to_hhmm(str(r.get("cutoff") or ""))
            if hhmm:
                return hhmm

    candidates: List[Tuple[int, str]] = []
    for r in race_times:
        hhmm = _to_hhmm(str(r.get("cutoff") or ""))
        if not hhmm:
            continue
        hm = _parse_hhmm(hhmm)
        if not hm:
            continue
        candidates.append((_minutes(hm[0], hm[1]), hhmm))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _detect_grade_label(venue: Dict[str, Any], races: List[Dict[str, Any]]) -> str:
    texts: List[str] = []

    for key in ["grade", "grade_label", "title", "subtitle", "series_name", "series_title", "event_name", "event_title"]:
        v = venue.get(key)
        if v:
            texts.append(str(v))

    for r in races[:12]:
        for key in ["name", "title"]:
            v = r.get(key)
            if v:
                texts.append(str(v))

    joined = " / ".join(texts)

    normalized = (
        joined.replace("Ｇ", "G")
              .replace("Ⅰ", "I")
              .replace("Ⅱ", "II")
              .replace("Ⅲ", "III")
              .upper()
    )

    if "SG" in normalized:
        return "SG"
    if "PG1" in normalized or "PGI" in normalized:
        return "G1"
    if "G1" in normalized or "GI" in normalized:
        return "G1"
    if "G2" in normalized or "GII" in normalized:
        return "G2"
    if "G3" in normalized or "GIII" in normalized:
        return "G3"

    return "一般"


def _resolve_grade_label(venue: Dict[str, Any], races: List[Dict[str, Any]]) -> str:
    direct = _normalize_grade_label(venue.get("grade_label"))
    if direct != "一般":
        return direct

    fallback = _normalize_grade_label(_detect_grade_label(venue, races))
    return fallback


def _classify_card_band(first_race_time: Optional[str]) -> str:
    if not first_race_time:
        return "normal"

    hm = _parse_hhmm(first_race_time)
    if not hm:
        return "normal"

    tmin = _minutes(hm[0], hm[1])

    if _minutes(8, 0) <= tmin <= _minutes(9, 0):
        return "morning"

    if _minutes(10, 0) <= tmin <= _minutes(12, 0):
        return "day"

    if _minutes(15, 0) <= tmin <= _minutes(16, 0):
        return "evening"

    if _minutes(17, 0) <= tmin <= _minutes(18, 0):
        return "night"

    return "normal"


def _legacy_card_tone(card_band: str) -> str:
    if card_band == "morning":
        return "morning"
    if card_band in {"evening", "night"}:
        return "night"
    return "normal"


def _is_true_final_race_text(text: str) -> bool:
    if not text:
        return False

    exclude_keywords = [
        "準優",
        "紹介",
        "インタビュー",
        "トライアル",
        "出場選手",
        "表彰",
        "戦線",
    ]
    if any(k in text for k in exclude_keywords):
        return False

    return "優勝戦" in text


def _is_final_day_by_races(races: List[Dict[str, Any]]) -> bool:
    for r in races:
        name = _normalize_text(r.get("name"))
        title = _normalize_text(r.get("title"))

        if _is_true_final_race_text(name) or _is_true_final_race_text(title):
            return True

    return False


def _resolve_day_label(venue: Dict[str, Any], races: List[Dict[str, Any]]) -> str:
    if _is_final_day_by_races(races):
        return "最終日"

    day_label = str(venue.get("day_label") or "").strip()
    if day_label:
        return day_label

    day = venue.get("day")
    if isinstance(day, int):
        if day == 1:
            return "初日"
        return f"{day}日目"

    return ""


def _sort_key(v: Dict[str, Any]):
    j = v.get("jcd") or ""
    try:
        return (0, int(j))
    except Exception:
        return (1, 999)


def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _safe_name(s: str) -> str:
    s = str(s or "").strip().replace(" ", "").replace("　", "")
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    return s


def _clear_json_files(dir_path: str) -> None:
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        return

    for name in os.listdir(dir_path):
        if name.lower().endswith(".json"):
            try:
                os.remove(os.path.join(dir_path, name))
            except Exception:
                pass


def build_site_payload(mbrace: Dict[str, Any], slot: str) -> Tuple[List[Dict[str, Any]], List[Tuple[str, Dict[str, Any]]]]:
    site_venues: List[Dict[str, Any]] = []
    venue_payloads: List[Tuple[str, Dict[str, Any]]] = []

    for venue in (mbrace.get("venues") or []):
        venue_name = str(venue.get("venue") or "").strip()
        if not venue_name:
            continue

        races = venue.get("races") or []
        race_times = _build_race_times(races)
        next_race, next_display = compute_next_from_race_times(race_times)
        grade_label = _resolve_grade_label(venue, races)
        first_race_time = _pick_first_race_time(race_times)
        card_band = _classify_card_band(first_race_time)
        day_label = _resolve_day_label(venue, races)

        row: Dict[str, Any] = {
            "slot": slot,
            "date": venue.get("date") or mbrace.get("date") or "",
            "name": venue_name,
            "jcd": VENUE_TO_JCD.get(venue_name, ""),
            "next_race": next_race,
            "next_display": next_display,
            "day": venue.get("day"),
            "total_days": venue.get("total_days"),
            "day_label": day_label,
            "grade_label": grade_label,
            "event_title": str(venue.get("event_title") or "").strip(),
            "first_race_time": first_race_time,
            "card_band": card_band,
            "card_tone": _legacy_card_tone(card_band),
            "race_times": race_times,
        }

        site_venues.append(row)

        races_out: List[Dict[str, Any]] = []
        for r in races:
            races_out.append({
                "rno": r.get("rno"),
                "name": r.get("name"),
                "cutoff": _to_hhmm(str(r.get("cutoff") or "")),
                "distance": r.get("distance_m"),
            })

        payload: Dict[str, Any] = {
            "slot": slot,
            "venue": venue_name,
            "date": venue.get("date") or mbrace.get("date") or "",
            "day": venue.get("day"),
            "total_days": venue.get("total_days"),
            "day_label": day_label,
            "grade_label": grade_label,
            "event_title": str(venue.get("event_title") or "").strip(),
            "first_race_time": first_race_time,
            "card_band": card_band,
            "card_tone": _legacy_card_tone(card_band),
            "race_times": race_times,
            "races": races_out,
        }

        venue_payloads.append((venue_name, payload))

    site_venues.sort(key=_sort_key)
    return site_venues, venue_payloads


def load_mbrace(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(OUT_VENUE_DIR, exist_ok=True)
    os.makedirs(OUT_VENUE_DIR_TODAY, exist_ok=True)
    os.makedirs(OUT_VENUE_DIR_TOMORROW, exist_ok=True)

    _clear_json_files(OUT_VENUE_DIR_TODAY)
    _clear_json_files(OUT_VENUE_DIR_TOMORROW)

    built_slots: Dict[str, List[Dict[str, Any]]] = {}
    compat_venue_payloads: Dict[str, Dict[str, Any]] = {}

    for src_path, slot in SRC_SPECS:
        mbrace = load_mbrace(src_path)
        if not mbrace:
            print(f"skip: {src_path} not found")
            built_slots[slot] = []
            continue

        site_venues, venue_payloads = build_site_payload(mbrace, slot)
        built_slots[slot] = site_venues

        if slot == "today":
            _write_json(OUT_VENUES_TODAY, site_venues)
        elif slot == "tomorrow":
            _write_json(OUT_VENUES_TOMORROW, site_venues)

        slot_dir = OUT_VENUE_DIR_TODAY if slot == "today" else OUT_VENUE_DIR_TOMORROW

        for venue_name, payload in venue_payloads:
            path = os.path.join(slot_dir, f"{_safe_name(venue_name)}.json")
            _write_json(path, payload)

            if venue_name not in compat_venue_payloads or slot == "today":
                compat_venue_payloads[venue_name] = payload

        print(f"site json build complete: {slot}")
        print(f"{slot} venues count:", len(site_venues))
        if site_venues:
            print(f"{slot} first venue:", site_venues[0])

    today_list = built_slots.get("today") or []
    tomorrow_list = built_slots.get("tomorrow") or []

    compat_list = today_list if today_list else tomorrow_list
    _write_json(OUT_VENUES_COMPAT, compat_list)

    for venue_name, payload in compat_venue_payloads.items():
        path = os.path.join(OUT_VENUE_DIR, f"{_safe_name(venue_name)}.json")
        _write_json(path, payload)

    print("compat venues.json count:", len(compat_list))
    print("compat venue files:", len(compat_venue_payloads))


if __name__ == "__main__":
    main()