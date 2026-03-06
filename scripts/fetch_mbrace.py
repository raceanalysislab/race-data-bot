# scripts/build_site_json.py
# mbrace_races_today.json からサイト用 venues.json を生成
# ※ venues.json は mbrace 一本
# ※ day / total_days が mbrace に入っていれば day_label も出力する

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

# 公式順 + jcd対応
VENUES = [
  {"jcd":"01","name":"桐生"}, {"jcd":"02","name":"戸田"}, {"jcd":"03","name":"江戸川"}, {"jcd":"04","name":"平和島"},
  {"jcd":"05","name":"多摩川"}, {"jcd":"06","name":"浜名湖"}, {"jcd":"07","name":"蒲郡"}, {"jcd":"08","name":"常滑"},
  {"jcd":"09","name":"津"}, {"jcd":"10","name":"三国"}, {"jcd":"11","name":"びわこ"}, {"jcd":"12","name":"住之江"},
  {"jcd":"13","name":"尼崎"}, {"jcd":"14","name":"鳴門"}, {"jcd":"15","name":"丸亀"}, {"jcd":"16","name":"児島"},
  {"jcd":"17","name":"宮島"}, {"jcd":"18","name":"徳山"}, {"jcd":"19","name":"下関"}, {"jcd":"20","name":"若松"},
  {"jcd":"21","name":"芦屋"}, {"jcd":"22","name":"福岡"}, {"jcd":"23","name":"唐津"}, {"jcd":"24","name":"大村"},
]
NAME_TO_JCD = {v["name"]: v["jcd"] for v in VENUES}

def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _hm_to_minutes(hm: str) -> Optional[int]:
    if not hm:
        return None
    s = str(hm).strip()
    if len(s) >= 5:
        s = s[:5]
    if ":" not in s:
        return None
    try:
        hh, mm = s.split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        return None

def _now_minutes_jst() -> int:
    n = datetime.now(JST)
    return n.hour * 60 + n.minute

def _pick_next_race(races: List[Dict[str, Any]], now_min: int) -> Tuple[Optional[int], Optional[str]]:
    """
    races: [{rno, cutoff("11:03"), ...}]
    return: (next_race, "HH:MM")
    """
    items: List[Tuple[int, int, str]] = []
    for r in races or []:
        rno = r.get("rno")
        cutoff = r.get("cutoff")
        tmin = _hm_to_minutes(cutoff)
        if isinstance(rno, int) and tmin is not None:
            items.append((tmin, rno, str(cutoff)[:5]))

    if not items:
        return (None, None)

    items.sort(key=lambda x: x[0])

    for tmin, rno, hm in items:
        if tmin > now_min:
            return (rno, hm)

    tmin, rno, hm = items[-1]
    return (rno, hm)

def _to_int(v: Any) -> Optional[int]:
    if isinstance(v, int):
        return v
    if v is None:
        return None
    m = re.search(r"(\d+)", str(v))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

def _extract_day_info(v: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """
    mbrace 側に day 情報が入ったとき用の受け口。
    今の JSON に無ければ (None, None) を返す。
    """

    current_day = None
    total_days = None

    current_keys = ["day", "current_day", "race_day", "day_no", "nichime"]
    total_keys = ["total_days", "series_days", "days", "total_day_count"]

    for key in current_keys:
        if key in v:
            current_day = _to_int(v.get(key))
            if current_day is not None:
                break

    for key in total_keys:
        if key in v:
            total_days = _to_int(v.get(key))
            if total_days is not None:
                break

    # 将来 text で入ってきた場合の保険
    text_candidates = [
        v.get("day_text"),
        v.get("series_text"),
        v.get("header"),
        v.get("title"),
        v.get("subtitle"),
        v.get("meta"),
    ]

    for text in text_candidates:
        s = str(text or "").strip()
        if not s:
            continue

        if current_day is None:
            m = re.search(r"(?:第\s*)?(\d+)\s*日目?", s)
            if m:
                current_day = _to_int(m.group(1))

        if total_days is None:
            m = re.search(r"(\d+)\s*日間", s)
            if m:
                total_days = _to_int(m.group(1))

        if current_day is None or total_days is None:
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

def main() -> None:
    src_path = os.path.join("data", "mbrace_races_today.json")
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"missing: {src_path}")

    src = _read_json(src_path)
    venues = src.get("venues") or []
    now_min = _now_minutes_jst()

    out: List[Dict[str, Any]] = []

    for v in venues:
        name = str(v.get("venue") or "").strip()
        races = v.get("races") or []
        if not name or not isinstance(races, list) or not races:
            continue

        jcd = NAME_TO_JCD.get(name)
        if not jcd:
            continue

        next_race, hm = _pick_next_race(races, now_min)
        if next_race is None or hm is None:
            continue

        current_day, total_days = _extract_day_info(v)
        day_label = _format_day_label(current_day, total_days)

        row: Dict[str, Any] = {
            "name": name,
            "jcd": jcd,
            "next_race": int(next_race),
            "next_display": f"{int(next_race)}R {hm}",
        }

        if current_day is not None:
            row["day"] = current_day
        if total_days is not None:
            row["total_days"] = total_days
        if day_label is not None:
            row["day_label"] = day_label

        out.append(row)

    order = {v["jcd"]: i for i, v in enumerate(VENUES)}
    out.sort(key=lambda x: order.get(x["jcd"], 999))

    dst_path = os.path.join("data", "site", "venues.json")
    _write_json(dst_path, out)

    print("built:", dst_path, "count=", len(out))

if __name__ == "__main__":
    main()