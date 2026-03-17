import csv
import json
import os


PLAYER_MASTER_PATH = os.path.join("data", "master", "players_master.json")
OUTPUT_CSV_PATH = os.path.join("data", "master", "racer_gender_template.csv")


def build_name(player: dict) -> str:
    name = str(player.get("name") or "").strip()
    if name:
        return name.replace(" ", "").replace("\u3000", "")

    sei = str(player.get("sei") or "").strip()
    mei = str(player.get("mei") or "").strip()
    full = f"{sei}{mei}".strip()
    return full.replace(" ", "").replace("\u3000", "")


def main() -> None:
    if not os.path.isfile(PLAYER_MASTER_PATH):
        raise FileNotFoundError(f"players_master.json が見つかりません: {PLAYER_MASTER_PATH}")

    with open(PLAYER_MASTER_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for regno, player in data.items():
        reg_str = str(regno).strip()
        if not reg_str.isdigit():
            continue

        name = build_name(player)
        rows.append((int(reg_str), name))

    rows.sort(key=lambda x: x[0])

    os.makedirs(os.path.dirname(OUTPUT_CSV_PATH), exist_ok=True)

    with open(OUTPUT_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["regno", "name", "female"])
        for regno, name in rows:
            writer.writerow([regno, name, ""])

    print(f"done: {OUTPUT_CSV_PATH}")
    print(f"rows: {len(rows)}")


if __name__ == "__main__":
    main()