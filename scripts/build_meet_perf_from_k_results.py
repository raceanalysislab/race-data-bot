import glob
import json
import os
import shutil
from collections import defaultdict
from typing import Any, Dict, List, Optional

INPUT = "data/k_results_parsed.json"
MBRACE_GLOB = "data/mbrace_races_*.json"
OUTPUT_DIR = "data/meet_perf"

DAY_COUNT = 7
SLOTS_PER_DAY = 2


def create_empty_days() -> List[List[Optional[Dict[str, Any]]]]:
    return [[None for _ in range(SLOTS_PER_DAY)] for _ in range(DAY_COUNT)]


def reset_output_dir(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def normalize_reg(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    if s.isdigit():
        return s.zfill(4)
    return s


def sort_races(races: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(races or [], key=lambda x: int(x.get("rno") or 0))


def load_target_dates_by_jcd() -> Dict[str, Dict[str, Any]]:
    targets: Dict[str, Dict[str, Any]] = {}

    venue_to_jcd = {
        "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
        "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
        "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
        "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
        "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
        "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
    }

    for path in sorted(glob.glob(MBRACE_GLOB)):
        if not os.path.isfile(path):
            continue

        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        venues = payload.get("venues", [])
        if not isinstance(venues, list):
            continue

        for v in venues:
            if not isinstance(v, dict):
                continue

            venue_name = str(v.get("venue") or "").strip()
            target_date = str(v.get("date") or "").strip()
            day_no = int(v.get("day") or 0) if v.get("day") is not None else 0
            event_title = str(v.get("event_title") or "").strip()
            event_title_norm = str(v.get("event_title_norm") or event_title).strip()

            raw_jcd = str(v.get("jcd") or "").strip()
            jcd = raw_jcd.zfill(2) if raw_jcd else ""

            if not jcd and venue_name:
                jcd = venue_to_jcd.get(venue_name, "")

            if not jcd or not target_date:
                continue

            targets[jcd] = {
                "jcd": jcd,
                "venue": venue_name,
                "date": target_date,
                "day_no": day_no,
                "event_title": event_title,
                "event_title_norm": event_title_norm,
            }

    return targets


def build_racers_from_k_days(
    k_days: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    racers: Dict[str, Dict[str, Any]] = {}

    for k_day in k_days:
        day_no = int(k_day.get("day_no") or 0)
        day_index = day_no - 1

        if not (0 <= day_index < DAY_COUNT):
            continue

        for race in sort_races(k_day.get("races") or []):
            for r in race.get("results") or []:
                reg = normalize_reg(r.get("reg"))
                if not reg:
                    continue

                if reg not in racers:
                    racers[reg] = {
                        "name": str(r.get("name") or "").strip(),
                        "days": create_empty_days(),
                    }

                slot = {
                    "course": r.get("course"),
                    "st": r.get("st"),
                    "rank": r.get("finish"),
                }

                slots = racers[reg]["days"][day_index]
                if slots[0] is None:
                    slots[0] = slot
                elif slots[1] is None:
                    slots[1] = slot

    return racers


def pick_same_series_previous_days(
    same_venue_days: List[Dict[str, Any]],
    current_day_no: int,
) -> List[Dict[str, Any]]:
    completed_days = max(0, current_day_no - 1)
    if completed_days <= 0:
        return []

    prev_days = [
        v for v in same_venue_days
        if isinstance(v.get("day_no"), int) or str(v.get("day_no") or "").isdigit()
    ]

    normalized: List[Dict[str, Any]] = []
    for v in prev_days:
        day_no = int(v.get("day_no") or 0)
        if 1 <= day_no <= completed_days:
            normalized.append(v)

    normalized.sort(key=lambda x: int(x.get("day_no") or 0))
    return normalized


def build_day_label(current_day_no: int) -> str:
    if current_day_no <= 0:
        return "—"
    if current_day_no == 1:
        return "初日"
    return f"{current_day_no}日目"


def main() -> None:
    if not os.path.exists(INPUT):
        print(f"missing input: {INPUT}")
        return

    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    venues = data.get("venues", [])
    print(f"venues: {len(venues)}")

    targets_by_jcd = load_target_dates_by_jcd()
    print(f"mbrace_targets: {len(targets_by_jcd)}")

    reset_output_dir(OUTPUT_DIR)

    venues_by_jcd: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for v in venues:
        raw_jcd = str(v.get("jcd") or "").strip()
        jcd = raw_jcd.zfill(2) if raw_jcd else ""
        if not jcd:
            continue
        venues_by_jcd[jcd].append(v)

    written = 0

    for jcd, target in targets_by_jcd.items():
        items = venues_by_jcd.get(jcd, [])
        if not items:
            print(f"skip_no_items: {jcd}")
            continue

        current_day_no = int(target.get("day_no") or 0)
        venue_name = str(target.get("venue") or "").strip()
        mbrace_date = str(target.get("date") or "").strip()
        event_title = str(target.get("event_title") or "").strip()
        event_title_norm = str(target.get("event_title_norm") or event_title).strip()

        if current_day_no <= 0 or not mbrace_date:
            print(f"skip_invalid_target: {jcd}")
            continue

        prev_days = pick_same_series_previous_days(items, current_day_no)

        print(
            f"target jcd={jcd} venue={venue_name} "
            f"mbrace_date={mbrace_date} current_day_no={current_day_no}"
        )
        print(f"picked_days: {[int(x.get('day_no') or 0) for x in prev_days]}")

        racers = build_racers_from_k_days(prev_days)

        out = {
            "jcd": jcd,
            "venue": venue_name,
            "date": mbrace_date,
            "day_no": current_day_no,
            "day_label": build_day_label(current_day_no),
            "total_days": None,
            "event_title": event_title,
            "event_title_norm": event_title_norm,
            "racers": racers,
        }

        filename = os.path.join(OUTPUT_DIR, f"{mbrace_date}_{jcd}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        written += 1
        print("OK:", filename)

    print(f"written: {written}")


if __name__ == "__main__":
    main()