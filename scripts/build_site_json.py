# scripts/build_site_json.py
# mbrace_races_today.json を正として site 用 JSON を生成する
# - data/site/venues.json : 開催中会場の一覧（mbraceに存在する会場）
# - data/site/venues/<会場>.json : 会場ごとのレース概要（rno/name/cutoff/distance）
#
# ※ venues_today.json（boatrace.jp由来）は不安定なので一切使わない

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

# ====== 会場名 → jcd（公式順） ======
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
    if len(s) < 4:
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

def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    if value is None:
        return None
    m = re.search(r"(\d+)", str(value))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

def _extract_day_info(venue: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """
    mbrace側の表記ゆれを吸収して current_day / total_days を拾う。
    まずはキー直取り、なければテキストから雑に拾う。
    """

    # 直接キー候補
    current_keys = ["day", "current_day", "race_day", "day_no", "nichime"]
    total_keys = ["total_days", "series_days", "days", "total_day_count"]

    current_day: Optional[int] = None
    total_days: Optional[int] = None

    for key in current_keys:
        if key in venue:
            current_day = _to_int(venue.get(key))
            if current_day is not None:
                break

    for key in total_keys:
        if key in venue:
            total_days = _to_int(venue.get(key))
            if total_days is not None:
                break

    # テキスト候補から補完
    text_candidates = [
        venue.get("day_text"),
        venue.get("series_text"),
        venue.get("title"),
        venue.get("subtitle"),
        venue.get("header"),
        venue.get("meta"),
    ]

    for text in text_candidates:
        s = str(text or "").strip()
        if not s:
            continue

        if current_day is None:
            # 例: 3日目 / 第3日
            m = re.search(r"(?:第\s*)?(\d+)\s*日目?", s)
            if m:
                current_day = _to_int(m.group(1))

        if total_days is None:
            # 例: 6日間
            m = re.search(r"(\d+)\s*日間", s)
            if m:
                total_days = _to_int(m.group(1))

        if current_day is None or total_days is None:
            # 例: 3/6
            m = re.search(r"(\d+)\s*/\s*(\d+)", s)
            if m:
                if current_day is None:
                    current_day = _to_int(m.group(1))
                if total_days is None:
                    total_days = _to_int(m.group(2))

    return current_day, total_days

def _format_day_label(current_day: Optional[int], total_days: Optional[int]) -> Optional[str]:
    if current_day is None:
        return None
    if current_day == 1:
        return "初日"
    if total_days is not None and current_day == total_days:
        return "最終日"
    return f"{current_day}日目"

def compute_next_from_races(races: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
    """
    mbraceの各レース cutoff(HH:MM)から「次の締切」を計算して
    next_race / next_display ("<rno>R HH:MM") を作る。
    """
    now = datetime.now(JST)
    now_min = _minutes(now.hour, now.minute)

    cushion = 2
    threshold = now_min - cushion

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
        return None, None

    candidates.sort(key=lambda x: x[0])

    for tmin, rno, hhmm in candidates:
        if tmin > threshold:
            return rno, f"{rno}R {hhmm}"

    return None, "終了"

def main():
    if not os.path.exists(MBRACE_PATH):
        raise FileNotFoundError(f"missing: {MBRACE_PATH}")

    with open(MBRACE_PATH, encoding="utf-8") as f:
        mbrace = json.load(f)

    site_venues: List[Dict[str, Any]] = []

    for venue in (mbrace.get("venues") or []):
        venue_name = str(venue.get("venue") or "").strip()
        if not venue_name:
            continue

        races = venue.get("races") or []
        next_race, next_display = compute_next_from_races(races)

        jcd = VENUE_TO_JCD.get(venue_name, "")
        current_day, total_days = _extract_day_info(venue)
        day_label = _format_day_label(current_day, total_days)

        row: Dict[str, Any] = {
            "name": venue_name,
            "jcd": jcd,
            "next_race": next_race,
            "next_display": next_display,
        }

        if current_day is not None:
            row["day"] = current_day
        if total_days is not None:
            row["total_days"] = total_days
        if day_label is not None:
            row["day_label"] = day_label

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

        current_day, total_days = _extract_day_info(venue)
        day_label = _format_day_label(current_day, total_days)

        races_out: List[Dict[str, Any]] = []
        for r in (venue.get("races") or []):
            races_out.append({
                "rno": r.get("rno"),
                "name": r.get("name"),
                "cutoff": r.get("cutoff"),
                "distance": r.get("distance_m"),
            })

        path = os.path.join(OUT_VENUE_DIR, f"{venue_name}.json")
        with open(path, "w", encoding="utf-8") as f:
            payload: Dict[str, Any] = {
                "venue": venue_name,
                "date": venue.get("date"),
                "races": races_out
            }
            if current_day is not None:
                payload["day"] = current_day
            if total_days is not None:
                payload["total_days"] = total_days
            if day_label is not None:
                payload["day_label"] = day_label

            json.dump(payload, f, ensure_ascii=False, indent=2)

    print("site json build complete")
    print("venues.json count:", len(site_venues))

if __name__ == "__main__":
    main()