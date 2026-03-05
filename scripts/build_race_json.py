# scripts/build_race_json.py
# data/mbrace_races_today.json → data/site/races/{jcd}_{rno}R.json を生成
# 互換：会場名ファイルも同時に出す（旧リンクが残ってても壊れない）
# 目的：URL/ファイル名を安定させる（会場名の表記ゆれ・文字化け・OS差を回避）

import json
import os
import re

SRC = "data/mbrace_races_today.json"
OUT = "data/site/races"

# 会場コード（公式順）
VENUE_TO_JCD = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}

def safe_name(s: str) -> str:
    """
    旧互換用のファイル名（会場名）を壊れにくくする。
    - スペース削除
    - OSで問題になりやすい記号を除去
    """
    s = str(s or "").strip().replace(" ", "").replace("　", "")
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    return s

def main():
    os.makedirs(OUT, exist_ok=True)

    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)

    venues = data.get("venues") or []
    created = 0
    skipped = 0

    for v in venues:
        venue_name = v.get("venue") or ""
        date = v.get("date") or data.get("date") or ""
        races = v.get("races") or []

        jcd = VENUE_TO_JCD.get(venue_name, "")
        if not jcd:
            # 会場名が想定外でも落とさず、会場名ベースは出せるようにする
            jcd = "00"

        for race in races:
            rno = race.get("rno")
            try:
                rno_i = int(rno)
            except Exception:
                skipped += 1
                continue

            out = {
                "venue": venue_name,
                "jcd": jcd if jcd != "00" else None,
                "date": date,
                "race": race,
            }

            # ✅ 安定ファイル名（推奨）：{jcd}_{rno}R.json
            stable_fname = f"{jcd}_{rno_i}R.json"
            stable_path = os.path.join(OUT, stable_fname)
            with open(stable_path, "w", encoding="utf-8") as wf:
                json.dump(out, wf, ensure_ascii=False, indent=2)
            created += 1

            # ✅ 旧互換：{venue}_{rno}R.json（リンクが残ってても壊れない）
            legacy_fname = f"{safe_name(venue_name)}_{rno_i}R.json"
            legacy_path = os.path.join(OUT, legacy_fname)
            if legacy_path != stable_path:
                with open(legacy_path, "w", encoding="utf-8") as wf:
                    json.dump(out, wf, ensure_ascii=False, indent=2)

    print("created:", created, "race json files")
    if skipped:
        print("skipped:", skipped)

if __name__ == "__main__":
    main()