# scripts/build_event_grade_candidates.py
# filtered済みイベント候補から SG / G1 / G2 / G3 の候補を振り分けて確認用JSONを作る
#
# 入力:
#   data/k_event_title_candidates_filtered.json
#
# 出力:
#   data/event_grade_candidates.json
#
# 目的:
# - event_master_manual.json を直接自動生成しない
# - まずは「候補」を出して人が確認できる形にする
# - 誤爆を減らしつつ、重賞候補だけを見る

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

JST = timezone(timedelta(hours=9))

SRC = "data/k_event_title_candidates_filtered.json"
DST = "data/event_grade_candidates.json"

# まずはここを育てていく
SG_KEYWORDS = [
    "グランプリ",
    "ダービー",
    "クラシック",
    "メモリアル",
    "チャレンジカップ",
    "クイーンズクライマックス",
    "オーシャンカップ",
    "ボートレースオールスター",
]

G2_KEYWORDS = [
    "MB大賞",
    "モーターボート大賞",
    "レディースチャレンジカップ",
    "レディースオールスター",
    "モーターボート誕生祭",
]

G3_KEYWORDS = [
    "ヴィーナスシリーズ",
    "オールレディース",
    "ルーキーシリーズ",
]

# G1は雑に「開設」だけ見ると誤爆するので、
# かなり限定した強い単語だけにする
G1_KEYWORDS_STRONG = [
    "周年記念",
    "開設記念競走",
    "開設記念 海の王者決定戦",
    "開設記念 北陸艇王決戦",
    "開設記念 海響王決定戦",
    "開設記念 びわこ大賞",
    "開設記念 ツッキー王座決定戦",
    "開設記念 赤城雷神杯",
    "開設記念 競帝王決定戦",
    "児島キングカップ",
    "尼崎センプルカップ",
    "京極賞",
    "大渦大賞",
    "太閤賞",
    "チャンピオンカップ",
    "クラウン争奪戦",
    "王座決定戦",
    "覇者決定戦",
    "王者決定戦",
]

# これは一般戦寄りが多いので G1 から除外
G1_EXCLUDE_KEYWORDS = [
    "BTS",
    "BP",
    "ボートピア",
    "オラレ",
    "外向発売所",
    "劇場開設記念",
    "開設記念令和スピードレーサー選抜戦",
    "日本財団会長杯",
    "スポーツニッポン杯",
    "ニッカン・コム杯",
    "富士通フロンテック杯",
    "市長杯",
    "金魚杯",
    "葉月杯",
    "マクール杯",
    "サンスポ",
    "TEL杯",
    "JESCO",
    "DS開設記念",
    "D・S開設記念",
]

MIN_OCCURRENCES = 2


def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def contains_any(title: str, keywords: List[str]) -> bool:
    return any(k in title for k in keywords)


def suggest_grade(title: str) -> Optional[str]:
    # 優先順が大事
    if contains_any(title, SG_KEYWORDS):
        return "SG"

    if contains_any(title, G2_KEYWORDS):
        return "G2"

    if contains_any(title, G3_KEYWORDS):
        return "G3"

    if contains_any(title, G1_EXCLUDE_KEYWORDS):
        return None

    if contains_any(title, G1_KEYWORDS_STRONG):
        return "G1"

    return None


def main():
    src = load_json(SRC)
    titles = src.get("titles") or []

    out_rows: List[Dict[str, Any]] = []

    for row in titles:
        if not isinstance(row, dict):
            continue

        title = str(row.get("title_key") or "").strip()
        if not title:
            continue

        occurrences = int(row.get("occurrences") or 0)
        if occurrences < MIN_OCCURRENCES:
            continue

        grade = suggest_grade(title)
        if not grade:
            continue

        out_rows.append({
            "title_key": title,
            "suggested_grade": grade,
            "occurrences": occurrences,
            "sample_titles": (row.get("sample_titles") or [])[:10],
            "sample_files": (row.get("sample_files") or [])[:20],
        })

    grade_order = {"SG": 0, "G1": 1, "G2": 2, "G3": 3}
    out_rows.sort(key=lambda x: (grade_order.get(x["suggested_grade"], 99), -x["occurrences"], x["title_key"]))

    payload = {
        "_meta": {
            "generated_at": datetime.now(JST).isoformat(),
            "source": SRC,
            "candidate_count": len(out_rows),
            "min_occurrences": MIN_OCCURRENCES,
            "policy": "suggest_only_manual_review_required",
        },
        "titles": out_rows,
    }

    os.makedirs("data", exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("out:", DST)
    print("candidate_count:", len(out_rows))


if __name__ == "__main__":
    main()