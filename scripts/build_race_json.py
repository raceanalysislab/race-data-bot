# scripts/build_race_json.py
# data/mbrace_races_today.json / data/mbrace_races_tomorrow.json
# → data/site/races/today/{jcd}_{rno}R.json
# → data/site/races/tomorrow/{jcd}_{rno}R.json
# 互換：会場名ファイルも同時に出す

import json
import os
import re
from typing import Any, Dict, List, Tuple

SRC_SPECS: List[Tuple[str, str]] = [
    ("data/mbrace_races_today.json", "today"),
    ("data/mbrace_races_tomorrow.json", "tomorrow"),
]

OUT_BASE = "data/site/races"

VENUE_TO_JCD = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}


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


def build_one(src_path: str, slot: str) -> Tuple[int, int]:
    out_dir = os.path.join(OUT_BASE, slot)
    _clear_json_files(out_dir)

    if not os.path.exists(src_path):
        print(f"skip: {src_path} not found")
        return 0, 0

    data = _load_json(src_path)

    venues: List[Dict[str, Any]] = data.get("venues") or []
    created = 0
    skipped = 0

    for v in venues:
        venue_name = str(v.get("venue") or "").strip()
        date = v.get("date") or data.get("date") or ""
        day = v.get("day")
        total_days = v.get("total_days")
        day_label = v.get("day_label")
        event_title = v.get("event_title") or ""
        grade_label = v.get("grade_label") or ""
        races = v.get("races") or []

        jcd = VENUE_TO_JCD.get(venue_name, "")
        if not jcd:
            jcd = "00"

        for race in races:
            rno = race.get("rno")
            try:
                rno_i = int(rno)
            except Exception:
                skipped += 1
                continue

            out: Dict[str, Any] = {
                "slot": slot,
                "venue": venue_name,
                "jcd": jcd if jcd != "00" else None,
                "date": date,
                "day": day,
                "total_days": total_days,
                "day_label": day_label,
                "event_title": event_title,
                "grade_label": grade_label,
                "race": race,
            }

            stable_fname = f"{jcd}_{rno_i}R.json"
            stable_path = os.path.join(out_dir, stable_fname)
            _write_json(stable_path, out)
            created += 1

            legacy_fname = f"{safe_name(venue_name)}_{rno_i}R.json"
            legacy_path = os.path.join(out_dir, legacy_fname)
            if legacy_path != stable_path:
                _write_json(legacy_path, out)

    print(f"slot: {slot}")
    print(f"source: {src_path}")
    print(f"created: {created} race json files")
    if skipped:
        print(f"skipped: {skipped}")

    return created, skipped


def main():
    total_created = 0
    total_skipped = 0

    os.makedirs(OUT_BASE, exist_ok=True)

    for src_path, slot in SRC_SPECS:
        created, skipped = build_one(src_path, slot)
        total_created += created
        total_skipped += skipped

    print("done")
    print("total_created:", total_created)
    if total_skipped:
        print("total_skipped:", total_skipped)


if __name__ == "__main__":
    main()