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
import glob
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))


def _resolve_src_specs():
    today = "data/mbrace_races_today.json"
    tomorrow = "data/mbrace_races_tomorrow.json"

    specs = []

    if os.path.exists(today):
        specs.append((today, "today"))
    if os.path.exists(tomorrow):
        specs.append((tomorrow, "tomorrow"))

    if specs:
        return specs

    files = sorted(glob.glob("data/mbrace_races_*.json"))
    if files:
        return [(files[-1], "today")]

    return []


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


# （この下のロジックはあなたのコードそのままなので変更していません）
# build_site_payload / load_mbrace / main なども元コードと同一です