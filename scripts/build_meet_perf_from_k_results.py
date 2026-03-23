import json
from collections import defaultdict
from datetime import datetime

INPUT = "data/k_results_parsed.json"
OUTPUT_DIR = "data/meet_perf/"

DAY_COUNT = 7
SLOTS_PER_DAY = 2


def create_empty_days():
    return [[None for _ in range(SLOTS_PER_DAY)] for _ in range(DAY_COUNT)]


def main():
    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    venues = data.get("venues", [])

    for v in venues:
        jcd = str(v.get("jcd")).zfill(2)
        date = v.get("date")
        day_no = int(v.get("day_no", 1))

        racers = {}

        # 選手ごとの枠を作る
        for race in v.get("races", []):
            for r in race.get("results", []):
                reg = str(r["reg"])

                if reg not in racers:
                    racers[reg] = {
                        "name": r["name"],
                        "days": create_empty_days()
                    }

        # レース結果を日配列に詰める
        for race in v.get("races", []):
            rno = race.get("rno")

            for r in race.get("results", []):
                reg = str(r["reg"])

                slot = {
                    "course": r.get("course"),
                    "st": r.get("st"),
                    "rank": r.get("finish")
                }

                day_index = day_no - 1

                # 1日2走まで
                slots = racers[reg]["days"][day_index]

                if slots[0] is None:
                    slots[0] = slot
                elif slots[1] is None:
                    slots[1] = slot
                # 3走目以降は無視

        out = {
            "date": date,
            "day_no": day_no,
            "racers": racers
        }

        filename = f"{OUTPUT_DIR}{date}_{jcd}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)

        print("OK:", filename)


if __name__ == "__main__":
    main()