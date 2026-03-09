import csv
import json
import requests
from pathlib import Path

# 公式CSVのURL（あとで本物に変更）
CSV_URL = "https://www.boatrace.jp/owpc/pc/data/download"

OUT_PATH = Path("data/site/players.json")


def fetch_csv():
    print("downloading csv...")
    r = requests.get(CSV_URL, timeout=30)
    r.raise_for_status()
    return r.content


def parse_csv(data):
    text = data.decode("shift_jis", errors="ignore")
    reader = csv.DictReader(text.splitlines())

    players = {}

    for row in reader:
        regno = row.get("登録番号") or row.get("登番")
        if not regno:
            continue

        players[str(regno)] = {
            "name": row.get("選手名"),
            "grade": row.get("級別"),
            "branch": row.get("支部"),
            "age": row.get("年齢"),
            "avg_st": row.get("平均ST"),
            "nat_win": row.get("全国勝率"),
            "local_win": row.get("当地勝率")
        }

    return players


def save_json(players):
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    print(f"saved: {OUT_PATH}")
    print(f"players: {len(players)}")


def main():
    data = fetch_csv()
    players = parse_csv(data)
    save_json(players)


if __name__ == "__main__":
    main()