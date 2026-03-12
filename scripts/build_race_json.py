# scripts/build_race_json.py
# data/mbrace_races_today.json / data/mbrace_races_tomorrow.json / data/mbrace_races_YYYY-MM-DD.json
# → data/site/races/YYYY-MM-DD/{jcd}_{rno}R.json
# 互換：会場名ファイルも同時に出す
# 追加：
#   data/master/merged_players.json を読み込み、
#   各艇に avg_st / st_count を付与する

import json
import os
import re
from typing import Any, Dict, List, Tuple

SRC_DIR = "data"
OUT_BASE = "data/site/races"
MERGED_PLAYERS_PATH = "data/master/merged_players.json"

VENUE_TO_JCD = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}

RE_SRC = re.compile(r"^mbrace_races_(today|tomorrow|\d{4}-\d{2}-\d{2})\.json$")


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


def _load_merged_players() -> Dict[str, Any]:
    if not os.path.exists(MERGED_PLAYERS_PATH):
        print(f"warn: merged players not found: {MERGED_PLAYERS_PATH}")
        return {}
    try:
        return _load_json(MERGED_PLAYERS_PATH)
    except Exception as e:
        print(f"warn: failed to load merged players: {e}")
        return {}


def _to_reg_key(v: Any) -> str:
    s = str(v or "").strip()
    return s if s.isdigit() else ""


def _merge_boat_stats(boat: Dict[str, Any], merged_players: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(boat)
    reg_key = _to_reg_key(out.get("regno"))

    if not reg_key:
        return out

    mp = merged_players.get(reg_key)
    if not isinstance(mp, dict):
        return out

    avg_st = mp.get("avg_st")
    st_count = mp.get("st_count")

    if avg_st is not None:
        out["avg_st"] = avg_st
    if st_count is not None:
        out["st_count"] = st_count

    return out


def _merge_race_stats(race: Dict[str, Any], merged_players: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(race)
    boats = out.get("boats") or []
    if not isinstance(boats, list):
        out["boats"] = []
        return out

    out["boats"] = [
        _merge_boat_stats(b, merged_players) if isinstance(b, dict) else b
        for b in boats
    ]
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


def _clear_out_base() -> None:
    if not os.path.isdir(OUT_BASE):
        os.makedirs(OUT_BASE, exist_ok=True)
        return

    for name in os.listdir(OUT_BASE):
        path = os.path.join(OUT_BASE, name)
        if os.path.isdir(path):
            try:
                for root, dirs, files in os.walk(path, topdown=False):
                    for fn in files:
                        os.remove(os.path.join(root, fn))
                    for dn in dirs:
                        os.rmdir(os.path.join(root, dn))
                os.rmdir(path)
            except Exception:
                pass


def build_one(src_path: str, merged_players: Dict[str, Any]) -> Tuple[int, int]:
    if not os.path.exists(src_path):
        print(f"skip: {src_path} not found")
        return 0, 0

    data = _load_json(src_path)
    top_date = str(data.get("date") or "").strip()

    if not top_date:
        print(f"skip: no top date in {src_path}")
        return 0, 0

    out_dir = os.path.join(OUT_BASE, top_date)
    os.makedirs(out_dir, exist_ok=True)

    venues: List[Dict[str, Any]] = data.get("venues") or []
    created = 0
    skipped = 0

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

        for race in races:
            rno = race.get("rno")
            try:
                rno_i = int(rno)
            except Exception:
                skipped += 1
                continue

            merged_race = _merge_race_stats(race, merged_players)

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

            stable_fname = f"{jcd}_{rno_i}R.json"
            stable_path = os.path.join(out_dir, stable_fname)
            _write_json(stable_path, out)
            created += 1

            legacy_fname = f"{safe_name(venue_name)}_{rno_i}R.json"
            legacy_path = os.path.join(out_dir, legacy_fname)
            if legacy_path != stable_path:
                _write_json(legacy_path, out)

    print(f"source: {src_path}")
    print(f"date: {top_date}")
    print(f"created: {created} race json files")
    if skipped:
        print(f"skipped: {skipped}")

    return created, skipped


def main():
    total_created = 0
    total_skipped = 0

    merged_players = _load_merged_players()
    print("merged_players:", len(merged_players))

    src_files = _collect_sources()
    print("source_files:", len(src_files))

    _clear_out_base()

    for src_path in src_files:
        created, skipped = build_one(src_path, merged_players)
        total_created += created
        total_skipped += skipped

    print("done")
    print("total_created:", total_created)
    if total_skipped:
        print("total_skipped:", total_skipped)


if __name__ == "__main__":
    main()