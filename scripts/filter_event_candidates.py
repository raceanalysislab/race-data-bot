# scripts/filter_event_candidates.py
# 重賞候補だけ抽出して別ファイルに出す

import json
import os

SRC = "data/k_event_title_candidates.json"
DST = "data/k_event_title_candidates_filtered.json"

# 🔥 このキーワードに引っかかるやつだけ残す
KEYWORDS = [
    "記念",
    "周年",
    "MB大賞",
    "ヴィーナス",
    "ルーキー",
    "レディース",
    "キングカップ",
    "センプル",
    "ダービー",
    "グランプリ",
    "クラシック",
    "メモリアル",
    "チャレンジカップ",
]

# 出現回数フィルタ（ノイズ除去）
MIN_OCCURRENCES = 5


def main():
    if not os.path.exists(SRC):
        raise FileNotFoundError(SRC)

    with open(SRC, "r", encoding="utf-8") as f:
        data = json.load(f)

    titles = data.get("titles", [])

    filtered = []

    for row in titles:
        title = row.get("title_key", "")
        occ = int(row.get("occurrences", 0))

        # 出現回数フィルタ
        if occ < MIN_OCCURRENCES:
            continue

        # キーワード一致
        if any(k in title for k in KEYWORDS):
            filtered.append(row)

    # occurrences順
    filtered.sort(key=lambda x: -int(x["occurrences"]))

    out = {
        "_meta": {
            "source": SRC,
            "filtered_count": len(filtered),
            "min_occurrences": MIN_OCCURRENCES,
            "keywords": KEYWORDS,
        },
        "titles": filtered,
    }

    os.makedirs("data", exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("out:", DST)
    print("filtered_count:", len(filtered))


if __name__ == "__main__":
    main()