import glob
import json
import os
import re
import shutil
from collections import defaultdict
from typing import Any, Dict, List, Optional

OUT_DIR = "data/meet_perf"
K_RESULTS_PATH = os.path.join("data", "k_results_parsed.json")

VENUE_NAME_TO_JCD = {
    "桐生": "01",
    "戸田": "02",
    "江戸川": "03",
    "平和島": "04",
    "多摩川": "05",
    "浜名湖": "06",
    "蒲郡": "07",
    "常滑": "08",
    "津": "09",
    "三国": "10",
    "びわこ": "11",
    "住之江": "12",
    "尼崎": "13",
    "鳴門": "14",
    "丸亀": "15",
    "児島": "16",
    "宮島": "17",
    "徳山": "18",
    "下関": "19",
    "若松": "20",
    "芦屋": "21",
    "福岡": "22",
    "唐津": "23",
    "大村": "24",
}

DAY_COUNT = 7
SLOTS_PER_DAY = 2


def norm_space(s: str) -> str:
    s = str(s or "")
    s = s.replace("　", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_event_title(title: str) -> str:
    s = norm_space(title)
    s = s.replace("～", "〜").replace("~", "〜")
    s = re.sub(r"第\s*\d+\s*回", "", s)
    s = re.sub(r"\bSG\b", "", s)
    s = re.sub(r"\bG[123]\b", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_name(name: str) -> str:
    return re.sub(r"[\s\u3000]+", "", str(name or "")).strip()


def normalize_regno(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    if s.isdigit():
        return str(int(s)).zfill(4)
    return s


def reset_out_dir(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_mbrace_json_files() -> List[str]:
    files = sorted(glob.glob(os.path.join("data", "mbrace_races_*.json")))
    return [p for p in files if os.path.isfile(p)]


def load_k_results() -> List[Dict[str, Any]]:
    if not os.path.exists(K_RESULTS_PATH):
        return []

    payload = read_json(K_RESULTS_PATH)
    venues = payload.get("venues") if isinstance(payload, dict) else None
    if not isinstance(venues, list):
        return []

    out: List[Dict[str, Any]] = []
    for item in venues:
        if isinstance(item, dict):
            out.append(item)
    return out


def build_current_racer_map_from_venue(venue_item: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    racers: Dict[str, Dict[str, Any]] = {}

    for race in venue_item.get("races") or []:
        for boat in race.get("boats") or []:
            regno = boat.get("regno")
            reg = normalize_regno(regno)
            if not reg:
                continue

            racers[reg] = {
                "name": normalize_name(boat.get("name") or ""),
            }

    return racers


def select_relevant_k_days(
    *,
    all_k_venues: List[Dict[str, Any]],
    venue_name: str,
    jcd: str,
    target_date: str,
    current_day_no: int,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for item in all_k_venues:
        item_jcd = str(item.get("jcd") or "").zfill(2)
        item_venue = str(item.get("venue") or "").strip()
        item_date = str(item.get("date") or "").strip()

        if not item_date or item_date >= target_date:
            continue

        if jcd and item_jcd != jcd:
            continue

        if venue_name and item_venue != venue_name:
            continue

        candidates.append(item)

    candidates.sort(key=lambda x: (x.get("date") or "", int(x.get("day_no") or 0)))

    completed_days = max(0, current_day_no - 1)
    if completed_days <= 0:
        return []

    if len(candidates) <= completed_days:
        return candidates

    return candidates[-completed_days:]


def build_empty_days() -> List[List[Optional[Dict[str, Any]]]]:
    return [[None for _ in range(SLOTS_PER_DAY)] for _ in range(DAY_COUNT)]


def put_result_into_day_slot(
    days: List[List[Optional[Dict[str, Any]]]],
    day_index: int,
    result_obj: Dict[str, Any],
) -> None:
    if not (0 <= day_index < DAY_COUNT):
        return

    for slot_idx in range(SLOTS_PER_DAY):
        if days[day_index][slot_idx] is None:
            days[day_index][slot_idx] = result_obj
            return


def build_racers_from_k_days(
    *,
    current_racers: Dict[str, Dict[str, Any]],
    k_days: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    racers: Dict[str, Dict[str, Any]] = {}

    for reg, meta in current_racers.items():
        racers[reg] = {
            "name": normalize_name(meta.get("name") or ""),
            "days": build_empty_days(),
        }

    for day_pos, k_day in enumerate(k_days):
        races = sorted(k_day.get("races") or [], key=lambda x: int(x.get("rno") or 0))
        bucket: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for race in races:
            for result in race.get("results") or []:
                reg = normalize_regno(result.get("reg"))
                if not reg:
                    continue

                bucket[reg].append({
                    "rno": int(race.get("rno") or 0),
                    "course": int(result.get("course") or 0) if result.get("course") else None,
                    "st": str(result.get("st") or "").strip(),
                    "rank": result.get("finish"),
                })

                if reg not in racers:
                    racers[reg] = {
                        "name": normalize_name(result.get("name") or ""),
                        "days": build_empty_days(),
                    }

        for reg, results in bucket.items():
            results.sort(key=lambda x: (x.get("rno") or 0))

            for item in results[:SLOTS_PER_DAY]:
                put_result_into_day_slot(
                    racers[reg]["days"],
                    day_pos,
                    {
                        "course": item.get("course"),
                        "st": item.get("st") or "",
                        "rank": item.get("rank"),
                    },
                )

    return racers


def build_day_label(current_day_no: int, total_days: Optional[int]) -> str:
    if current_day_no <= 0:
        return "—"
    if current_day_no == 1:
        return "初日"
    if total_days is not None and current_day_no == total_days:
        return "最終日"
    return f"{current_day_no}日目"


def build_payload_for_venue(
    *,
    venue_item: Dict[str, Any],
    all_k_venues: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    venue_name = str(venue_item.get("venue") or "").strip()
    target_date = str(venue_item.get("date") or "").strip()
    event_title = str(venue_item.get("event_title") or "").strip()
    current_day_no = int(venue_item.get("day") or 0) if venue_item.get("day") is not None else 0
    total_days_raw = venue_item.get("total_days")
    total_days = int(total_days_raw) if total_days_raw is not None else None
    jcd = VENUE_NAME_TO_JCD.get(venue_name, "")

    if not venue_name or not target_date or not jcd:
        return None

    current_racers = build_current_racer_map_from_venue(venue_item)

    k_days = select_relevant_k_days(
        all_k_venues=all_k_venues,
        venue_name=venue_name,
        jcd=jcd,
        target_date=target_date,
        current_day_no=current_day_no,
    )

    racers = build_racers_from_k_days(
        current_racers=current_racers,
        k_days=k_days,
    )

    racers_out: Dict[str, Any] = {}
    for reg, row in sorted(racers.items(), key=lambda x: x[0]):
        racers_out[reg] = {
            "name": row.get("name") or "",
            "days": row.get("days") or build_empty_days(),
        }

    return {
        "jcd": jcd,
        "venue": venue_name,
        "date": target_date,
        "day_no": current_day_no,
        "day_label": venue_item.get("day_label") or build_day_label(current_day_no, total_days),
        "total_days": total_days,
        "event_title": event_title,
        "event_title_norm": venue_item.get("event_title_norm") or normalize_event_title(event_title),
        "racers": racers_out,
    }


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    mbrace_files = collect_mbrace_json_files()
    if not mbrace_files:
        print("no mbrace json files")
        return

    reset_out_dir(OUT_DIR)
    all_k_venues = load_k_results()

    written = 0

    for path in mbrace_files:
        payload = read_json(path)
        venues = payload.get("venues") if isinstance(payload, dict) else None
        if not isinstance(venues, list):
            continue

        for venue_item in venues:
            if not isinstance(venue_item, dict):
                continue

            out_data = build_payload_for_venue(
                venue_item=venue_item,
                all_k_venues=all_k_venues,
            )
            if not out_data:
                continue

            out_path = os.path.join(
                OUT_DIR,
                f"{out_data['date']}_{out_data['jcd']}.json"
            )
            write_json(out_path, out_data)
            written += 1

    print(f"mbrace_files: {len(mbrace_files)}")
    print(f"k_venues: {len(all_k_venues)}")
    print(f"written: {written}")


if __name__ == "__main__":
    main()