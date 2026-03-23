import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

INPUT = "data/k_results_parsed.json"
OUTPUT_DIR = "data/meet_perf"

DAY_COUNT = 7
SLOTS_PER_DAY = 2


def create_empty_days() -> List[List[Optional[Dict[str, Any]]]]:
    return [[None for _ in range(SLOTS_PER_DAY)] for _ in range(DAY_COUNT)]


def parse_date(s: str) -> datetime.date:
    return datetime.strptime(str(s), "%Y-%m-%d").date()


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


def build_racers_from_days(days_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    racers: Dict[str, Dict[str, Any]] = {}

    for day_index, venue_day in enumerate(days_data):
        for race in sort_races(venue_day.get("races") or []):
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


def pick_contiguous_previous_days(same_venue_days: List[Dict[str, Any]], target_date: str) -> List[Dict[str, Any]]:
    target_dt = parse_date(target_date)

    prev_days = [
        v for v in same_venue_days
        if str(v.get("date") or "").strip() < target_date
    ]
    prev_days.sort(key=lambda x: str(x.get("date") or ""))

    if not prev_days:
        return []

    by_date = {}
    for v in prev_days:
        d = str(v.get("date") or "").strip()
        by_date[d] = v

    picked: List[Dict[str, Any]] = []
    cursor = target_dt - timedelta(days=1)

    while True:
        key = cursor.strftime("%Y-%m-%d")
        if key not in by_date:
            break
        picked.append(by_date[key])
        cursor -= timedelta(days=1)

    picked.reverse()
    return picked[:DAY_COUNT]


def main() -> None:
    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    venues = data.get("venues", [])
    reset_output_dir(OUTPUT_DIR)

    venues_by_jcd: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for v in venues:
        jcd = str(v.get("jcd") or "").zfill(2)
        if not jcd:
            continue
        venues_by_jcd[jcd].append(v)

    for jcd, items in venues_by_jcd.items():
        items.sort(key=lambda x: str(x.get("date") or ""))

        for target in items:
            target_date = str(target.get("date") or "").strip()
            day_no = int(target.get("day_no") or 1)

            if not target_date:
                continue

            prev_days = pick_contiguous_previous_days(items, target_date)

            racers = build_racers_from_days(prev_days)

            out = {
                "jcd": jcd,
                "date": target_date,
                "day_no": day_no,
                "racers": racers,
            }

            filename = os.path.join(OUTPUT_DIR, f"{target_date}_{jcd}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)

            print("OK:", filename)


if __name__ == "__main__":
    main()