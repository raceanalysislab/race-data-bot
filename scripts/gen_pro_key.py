# scripts/gen_pro_key.py
# data/pro_key.json を毎日JST基準で更新（1日固定キー）

import json
import os
from datetime import datetime, timezone, timedelta
import secrets

JST = timezone(timedelta(hours=9))
OUT_PATH = os.path.join("data", "pro_key.json")

def main():
    now = datetime.now(JST)
    today = now.strftime("%Y%m%d")
    updated_at = now.strftime("%Y-%m-%d %H:%M:%S")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    # 既存ファイルがあるか確認
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)

        # 今日と同じ日付ならキーを再利用
        if existing.get("date") == today:
            print("Same day detected. Keeping existing key.")
            existing["updated_at"] = updated_at

            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            return

    # 新しいキー生成（6桁）
    key = f"{secrets.randbelow(1_000_000):06d}"

    out = {
        "date": today,
        "key": key,
        "updated_at": updated_at,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Generated new key: {key}")

if __name__ == "__main__":
    main()