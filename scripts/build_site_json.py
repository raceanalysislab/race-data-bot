# scripts/build_site_json.py
# mbrace_races_today.json を正として site 用 JSON を生成する
# - data/site/venues.json : 開催中会場の一覧
# - data/site/venues/<会場>.json : 会場ごとのレース概要
#
# 追加:
# - grade_label（一般戦 / G3 / G2 / G1 / SG / PG1 / ルーキー / レディース など）
# - card_tone（normal / morning / night）
#   → app.js / grid.css 側で表示・色分けに使えるようにする

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

MBRACE_PATH = "data/mbrace_races_today.json"

OUT_DIR = "data/site"
OUT_VENUES = os.path.join(OUT_DIR, "venues.json")
OUT_VENUE_DIR = os.path.join(OUT_DIR, "venues")

os.makedirs(OUT_VENUE_DIR, exist_ok=True)

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
    if len(s) < 4 or ":" not in s:
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

def compute_next_from_races(races: List[Dict[str, Any]]) -> Tuple[Optional[int], str]:
    now = datetime.now(JST)
    now_min = _minutes(now.hour, now.minute)

    candidates: List[Tuple[int, int, str]] = []
    for r in races:
        rno = r.get("rno")
        cutoff = r.get("cutoff")

        if not isinstance(rno, int):
            continue

        hm = _parse_hhmm(str(cutoff or ""))
        if not hm:
            continue

        tmin = _minutes(hm[0], hm[1])
        candidates.append((tmin, rno, f"{_pad2(hm[0])}:{_pad2(hm[1])}"))

    if not candidates:
        return None, "発売終了"

    candidates.sort(key=lambda x: x[0])

    for tmin, rno, hhmm in candidates:
        if tmin > now_min:
            return rno, f"{rno}R {hhmm}"

    return None, "発売終了"

def _detect_grade_label(venue: Dict[str, Any], races: List[Dict[str, Any]]) -> str:
    texts: List[str] = []

    for key in ["grade", "grade_label", "title", "subtitle", "series_name", "series_title", "event_name"]:
        v = venue.get(key)
        if v:
            texts.append(str(v))

    for r in races[:3]:
        for key in ["name", "title"]:
            v = r.get(key)
            if v:
                texts.append(str(v))

    joined = " / ".join(texts)

    upper = joined.upper()

    if "PG1" in upper:
        return "PG1"
    if re.search(r"\bSG\b", upper):
        return "SG"
    if re.search(r"\bG1\b", upper):
        return "G1"
    if re.search(r"\bG2\b", upper):
        return "G2"
    if re.search(r"\bG3\b", upper):
        return "G3"

    if any(k in joined for k in ["オールレディース", "レディース", "ヴィーナス", "女子戦", "クイーンズ"]):
        return "レディース"

    if any(k in joined for k in ["ルーキー", "ヤングダービー", "スカパー!・JLC杯ルーキーシリーズ"]):
        return "ルーキー"

    if any(k in joined for k in ["企業杯", "モーターボート大賞", "地区選"]):
        return "一般戦"

    return "一般戦"

def _detect_card_tone(next_display: str) -> str:
    if not isinstance(next_display, str):
        return "normal"

    m = re.search(r"(\d{1,2}):(\d{2})", next_display)
    if not m:
        return "normal"

    hh = int(m.group(1))
    mm = int(m.group(2))
    tmin = _minutes(hh, mm)

    if tmin < _minutes(12, 0):
        return "morning"
    if tmin >= _minutes(17, 0):
        return "night"
    return "normal"

def main():
    if not os.path.exists(MBRACE_PATH):
        raise FileNotFoundError(f"missing: {MBRACE_PATH}")

    with open(MBRACE_PATH, "r", encoding="utf-8") as f:
        mbrace = json.load(f)

    site_venues: List[Dict[str, Any]] = []

    for venue in (mbrace.get("venues") or []):
        venue_name = str(venue.get("venue") or "").strip()
        if not venue_name:
            continue

        races = venue.get("races") or []
        next_race, next_display = compute_next_from_races(races)
        grade_label = _detect_grade_label(venue, races)
        card_tone = _detect_card_tone(next_display)

        row: Dict[str, Any] = {
            "name": venue_name,
            "jcd": VENUE_TO_JCD.get(venue_name, ""),
            "next_race": next_race,
            "next_display": next_display,
            "day": venue.get("day"),
            "total_days": venue.get("total_days"),
            "day_label": venue.get("day_label"),
            "grade_label": grade_label,
            "card_tone": card_tone,
        }

        site_venues.append(row)

    def sort_key(v: Dict[str, Any]):
        j = v.get("jcd") or ""
        try:
            return (0, int(j))
        except Exception:
            return (1, 999)

    site_venues.sort(key=sort_key)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_VENUES, "w", encoding="utf-8") as f:
        json.dump(site_venues, f, ensure_ascii=False, indent=2)

    for venue in (mbrace.get("venues") or []):
        venue_name = str(venue.get("venue") or "").strip()
        if not venue_name:
            continue

        races = venue.get("races") or []
        grade_label = _detect_grade_label(venue, races)

        races_out: List[Dict[str, Any]] = []
        for r in races:
            races_out.append({
                "rno": r.get("rno"),
                "name": r.get("name"),
                "cutoff": r.get("cutoff"),
                "distance": r.get("distance_m"),
            })

        payload: Dict[str, Any] = {
            "venue": venue_name,
            "date": venue.get("date"),
            "day": venue.get("day"),
            "total_days": venue.get("total_days"),
            "day_label": venue.get("day_label"),
            "grade_label": grade_label,
            "races": races_out,
        }

        path = os.path.join(OUT_VENUE_DIR, f"{venue_name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    print("site json build complete")
    print("venues.json count:", len(site_venues))
    if site_venues:
        print("first venue:", site_venues[0])

if __name__ == "__main__":
    main()