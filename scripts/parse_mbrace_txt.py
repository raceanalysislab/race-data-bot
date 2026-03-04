# scripts/parse_mbrace_txt.py
# mbrace番組表txt → JSON
# 出力: data/mbrace_races_today.json

import json
import os
import re
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional

JST = timezone(timedelta(hours=9))

# 全角 → 半角変換（必要最低限）
TRANS = str.maketrans({
    "０":"0","１":"1","２":"2","３":"3","４":"4","５":"5","６":"6","７":"7","８":"8","９":"9",
    "Ｒ":"R","Ｈ":"H","ｍ":"m","：":":","　":" "
})

def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# レースヘッダ
RE_RACE_HEAD = re.compile(
    r"^\s*([0-9]{1,2})R\s+(.+?)\s+(進入固定|進入自由)?\s*H?([0-9]{3,4})m.*?締切予定\s*([0-9]{1,2}:[0-9]{2})"
)

# 選手行
RE_BOAT_LINE = re.compile(
    r"^\s*([1-6])\s+(\d{4})\s*(\S+?)\s*([0-9]{1,2})\s*([^\d\s]{2,6})\s*([0-9]{2})\s*(A1|A2|B1|B2)\s+"
    r"([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})\s+"
    r"([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(\d{1,2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(\d{1,2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(.*)$"
)

def read_text_auto(path: str) -> List[str]:
    # mbrace txt は cp932 のことが多い
    for enc in ["cp932", "utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.readlines()
        except Exception:
            pass
    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return f.readlines()

def infer_txt_path() -> str:
    """
    data/source_final_url.txt にある .lzh URL から日付(YYMMDD)を抽出し、
    data/extract/bYYMMDD.txt を読みに行く。
    例: .../202603/b260303.lzh -> b260303.txt
    """
    p = os.path.join("data", "source_final_url.txt")
    if not os.path.exists(p):
        # 最低限のフォールバック（従来）
        return os.path.join("data", "extract", "b260303.txt")

    url = ""
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        url = (f.read() or "").strip()

    m = re.search(r"/b(\d{6})\.lzh", url)
    if not m:
        return os.path.join("data", "extract", "b260303.txt")

    yymmdd = m.group(1)
    return os.path.join("data", "extract", f"b{yymmdd}.txt")

def parse_venue_from_line(l: str) -> str:
    """
    "ボートレース大 村 3月 3日 ..." みたいな行から場名だけ抜く
    """
    # 「ボートレース」以降の最初のトークンを取る（空白はnorm済み想定）
    m = re.search(r"ボートレース\s*([^\s]+)", l)
    if not m:
        return ""
    v = m.group(1)
    v = v.replace(" ", "")
    return v

def parse_file(txt_path: str) -> Dict[str, Any]:
    lines_raw = read_text_auto(txt_path)
    lines = [norm(l) for l in lines_raw if l.strip()]

    venue = ""
    ymd = ""

    # まずヘッダ付近から venue / date を拾う
    for l in lines[:80]:
        if (not venue) and ("ボートレース" in l):
            v = parse_venue_from_line(l)
            if v:
                venue = v

        # 年月日（最優先）
        m = re.search(r"(\d{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日", l)
        if m:
            y, mo, d = m.groups()
            ymd = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            break

    # 年が取れない場合は、月日だけから補完（今年扱い）
    if not ymd:
        for l in lines[:120]:
            m2 = re.search(r"([0-9]{1,2})月\s*([0-9]{1,2})日", l)
            if m2:
                mo, d = m2.groups()
                y = datetime.now(JST).year
                try:
                    ymd = f"{y:04d}-{int(mo):02d}-{int(d):02d}"
                    break
                except Exception:
                    pass

    races: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    for l in lines:
        mh = RE_RACE_HEAD.search(l)
        if mh:
            if cur:
                races.append(cur)

            cur = {
                "rno": int(mh.group(1)),
                "name": mh.group(2).strip(),
                "shinin": (mh.group(3) or "").strip(),
                "distance_m": int(mh.group(4)),
                "cutoff": mh.group(5),
                "boats": []
            }
            continue

        if not cur:
            continue

        mb = RE_BOAT_LINE.match(l)
        if mb:
            (waku, regno, name, age, branch, weight, grade,
             nat_win, nat_2, loc_win, loc_2,
             motor_no, motor_2, boat_no, boat_2, rest) = mb.groups()

            cur["boats"].append({
                "waku": int(waku),
                "regno": int(regno),
                "name": name.replace(" ", ""),
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

    return {
        "source": os.path.basename(txt_path),
        "venue": venue,
        "date": ymd,
        "parsed_at": datetime.now(JST).isoformat(),
        "races": races,
    }

def classify_race(race: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    nm = race.get("name", "") or ""

    # 女子戦（安全：文字がある時だけ）
    if any(k in nm for k in ["女子", "レディース", "ヴィーナス", "クイーン", "オールレディース"]):
        tags.append("女子戦")

    boats = race.get("boats") or []
    if boats:
        b2 = sum(1 for b in boats if b.get("grade") == "B2")
        low = sum(1 for b in boats if (b.get("nat_win") or 0) <= 3.0)

        if b2 >= 2:
            tags.append("新人多め")

        if (b2 >= 2 and low >= 3) or (low >= 5):
            tags.append("荒れ注意")

        one = next((b for b in boats if b.get("waku") == 1), None)
        if one and (one.get("nat_win") or 0) >= 6.0:
            weak = sum(1 for b in boats if b.get("waku") != 1 and (b.get("nat_win") or 0) <= 4.0)
            if weak >= 4:
                tags.append("鉄板寄り")

    return tags

def main():
    txt_path = infer_txt_path()

    data = parse_file(txt_path)

    for r in data["races"]:
        r["tags"] = classify_race(r)

    out_path = os.path.join("data", "mbrace_races_today.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("txt:", txt_path)
    print("venue:", data["venue"])
    print("date:", data["date"])
    print("races:", len(data["races"]))

if __name__ == "__main__":
    main()