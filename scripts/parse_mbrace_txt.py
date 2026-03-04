# scripts/parse_mbrace_txt.py
# mbraceの番組表 txt (STARTB ... ENDB想定) をパースして JSON化する
# 出力: data/mbrace_races_today.json
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

JST = timezone(timedelta(hours=9))

ZEN2HAN = str.maketrans("０１２３４５６７８９：", "0123456789:")
RE_RACE_HEAD = re.compile(
    r"^\s*([0-9]{1,2})Ｒ\s+(.+?)\s+(進入固定|進入自由)?\s*Ｈ?([0-9]{3,4})ｍ.*?締切予定([0-9]{1,2}：[0-9]{2})"
)
RE_BOAT_LINE = re.compile(
    r"^\s*([1-6])\s+(\d{4})\s*(\S+?)\s*([0-9]{1,2})\s*([^\d\s]{2,6})\s*([0-9]{2})\s*(A1|A2|B1|B2)\s+"
    r"([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})\s+"
    r"([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(\d{1,2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(\d{1,2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(.*)$"
)

def norm(s: str) -> str:
    return (s or "").translate(ZEN2HAN)

def parse_file(txt_path: str) -> Dict[str, Any]:
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.rstrip("\n") for l in f]

    # メタ（場名 / 日付）
    venue = ""
    ymd = ""
    for l in lines[:40]:
        if "ボートレース" in l and ("月" in l and "日" in l):
            # 例: "ボートレース大　村   　３月　３日 ..."
            venue = re.sub(r"\s+", "", l.split("月")[0])
            venue = venue.replace("ボートレース", "")
        # 年月日がどこかにある: "２０２６年　３月　３日"
        m = re.search(r"(\d{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日", norm(l))
        if m:
            y, mo, d = m.groups()
            ymd = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            break

    races: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    for raw in lines:
        l = norm(raw)

        mh = RE_RACE_HEAD.search(l)
        if mh:
            # 前のレースを確定
            if cur:
                races.append(cur)

            rno = int(mh.group(1))
            rname = mh.group(2).strip()
            shinin = (mh.group(3) or "").strip()
            dist_m = int(mh.group(4))
            cutoff = mh.group(5).strip()  # "15:20"

            cur = {
                "rno": rno,
                "name": rname,
                "shinin": shinin,       # 進入固定/進入自由
                "distance_m": dist_m,
                "cutoff": cutoff,
                "boats": []
            }
            continue

        if not cur:
            continue

        mb = RE_BOAT_LINE.match(l)
        if mb:
            (waku, regno, name, age, branch, weight, grade,
             nat_win, nat_2, loc_win, loc_2,
             motor_no, motor_2, boat_no, boat_2,
             rest) = mb.groups()

            # 今節成績などは崩れやすいので“そのまま文字列保持”
            cur["boats"].append({
                "waku": int(waku),
                "regno": int(regno),
                "name": name.replace("　", ""),  # 全角空白消し
                "age": int(age),
                "branch": branch,
                "weight": int(weight),
                "grade": grade,
                "nat_win": float(nat_win),
                "nat_2": float(nat_2),
                "loc_win": float(loc_win),
                "loc_2": float(loc_2),
                "motor_no": int(motor_no),
                "motor_2": float(motor_2),
                "boat_no": int(boat_no),
                "boat_2": float(boat_2),
                "note": rest.strip(),
            })

    if cur:
        races.append(cur)

    out = {
        "source": os.path.basename(txt_path),
        "venue": venue,
        "date": ymd,
        "parsed_at": datetime.now(JST).isoformat(),
        "races": races,
    }
    return out

def classify_race(race: Dict[str, Any]) -> List[str]:
    """
    Pro向けタグ（暫定版）
    ※女子判定は“テキストに女子/レディース等がある場合のみ”で安全運用
    """
    tags: List[str] = []

    nm = race.get("name", "")
    nm2 = nm.replace("　", "")

    # 女子戦（レース名/節内表記に依存）
    if any(k in nm2 for k in ["女子", "レディース", "ヴィーナス", "クイーン", "オールレディース"]):
        tags.append("女子戦")

    boats = race.get("boats") or []
    if boats:
        b2 = sum(1 for b in boats if b.get("grade") == "B2")
        low_rate = sum(1 for b in boats if (b.get("nat_win") or 0) <= 3.0)

        # 新人戦（暫定：B2が多い / 勝率低いが多い）
        if b2 >= 2 or low_rate >= 4:
            tags.append("新人多め")

        # 荒れ（暫定：B2多い + 低勝率多い）
        if (b2 >= 2 and low_rate >= 3) or (low_rate >= 5):
            tags.append("荒れ注意")

        # 鉄板（暫定：1号艇がそこそこ強い + 周りが弱い）
        one = next((b for b in boats if b.get("waku") == 1), None)
        if one:
            one_win = one.get("nat_win") or 0
            others_win = [b.get("nat_win") or 0 for b in boats if b.get("waku") != 1]
            if one_win >= 6.0 and sum(1 for x in others_win if x <= 4.0) >= 4:
                tags.append("鉄板寄り")

    return tags

def main():
    # 例: data/extract/b260303.txt を読む
    # “今日のファイル名”は別ロジックで決めて渡してOK（source_final_url.txt運用でもOK）
    txt_path = os.path.join("data", "extract", "b260303.txt")

    data = parse_file(txt_path)

    # タグ付け（Proの入口）
    for r in data["races"]:
        r["tags"] = classify_race(r)

    out_path = os.path.join("data", "mbrace_races_today.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"wrote: {out_path} races={len(data['races'])}")

if __name__ == "__main__":
    main()