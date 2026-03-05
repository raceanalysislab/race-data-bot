# scripts/build_site_json.py
# mbrace_races_today.json を正として site 用 JSON を生成する
# - data/site/venues.json : 開催中会場の一覧（mbraceに存在する会場）
# - data/site/venues/<会場>.json : 会場ごとのレース概要（rno/name/cutoff/distance）
#
# ※ venues_today.json（boatrace.jp由来）は不安定なので一切使わない

import json
import os
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

def compute_next_from_races(races: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
    """
    mbraceの各レース cutoff(HH:MM)から「次の締切」を計算して
    next_race / next_display ("<rno>R HH:MM") を作る。
    """
    now = datetime.now(JST)
    now_min = _minutes(now.hour, now.minute)

    # 1〜2分のズレ保険（bot更新遅れ/時計差）
    # cutoffと同分でも「まだ次」として扱うなら -1〜-2 くらいが安全
    cushion = 2
    threshold = now_min - cushion

    candidates: List[Tuple[int, int, str]] = []  # (tMin, rno, hhmm)
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

    # すべて締切済み
    return None, "終了"

def main():
    if not os.path.exists(MBRACE_PATH):
        raise FileNotFoundError(f"missing: {MBRACE_PATH}")

    with open(MBRACE_PATH, encoding="utf-8") as f:
        mbrace = json.load(f)

    # --- venues.json（トップ用：mbraceに存在する会場＝開催扱い） ---
    site_venues: List[Dict[str, Any]] = []

    for venue in (mbrace.get("venues") or []):
        venue_name = str(venue.get("venue") or "").strip()
        if not venue_name:
            continue

        races = venue.get("races") or []
        next_race, next_display = compute_next_from_races(races)

        jcd = VENUE_TO_JCD.get(venue_name, "")
        site_venues.append({
            "name": venue_name,
            "jcd": jcd,
            "next_race": next_race,
            "next_display": next_display,
        })

    # 公式アプリ順で並べる（jcdあるもの優先、なければ最後）
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

    # --- 会場ごとのレース概要（既存のまま） ---
    for venue in (mbrace.get("venues") or []):
        venue_name = str(venue.get("venue") or "").strip()
        if not venue_name:
            continue

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
            json.dump({
                "venue": venue_name,
                "date": venue.get("date"),
                "races": races_out
            }, f, ensure_ascii=False, indent=2)

    print("site json build complete")
    print("venues.json count:", len(site_venues))

if __name__ == "__main__":
    main()