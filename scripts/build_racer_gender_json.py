import csv
import json
import os

SRC = "data/master/racer_gender_template.csv"
OUT = "data/master/racer_gender.json"


def main():
    result = {}

    with open(SRC, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            regno = str(row.get("regno", "")).strip()
            female = str(row.get("female", "")).strip()

            if not regno:
                continue

            result[regno] = 1 if female == "1" else 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("written:", OUT)
    print("count:", len(result))
    print("female_count:", sum(1 for v in result.values() if v == 1))


if __name__ == "__main__":
    main()