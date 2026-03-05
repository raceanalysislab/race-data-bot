# scripts/parse_mbrace_txt.py
# mbrace番組表txt（STARTB...ENDB想定）→ 会場ごとにパースしてJSON化
# 出力: data/mbrace_races_today.json

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

# 全角 → 半角変換（必要最低限）
TRANS = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "Ｒ": "R", "Ｈ": "H", "ｍ": "m", "：": ":", "　": " "
})

def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# レースヘッダ（例: "1R 一般 進入固定 H1800m ... 締切予定15:20"）
RE_RACE_HEAD = re.compile(
    r"^\s*([0-9]{1,2})R\s+(.+?)\s+(進入固定|進入自由)?\s*H?([0-9]{3,4})m.*?締切予定\s*([0-9]{1,2}:[0-9]{2})"
)

# 選手行（現状の形に合わせる）
RE_BOAT_LINE = re.compile(
    r"^\s*([1-6])\s+(\d{4})\s*(\S+?)\s*([0-9]{1,2})\s*([^\d\s]{2,6})\s*([0-9]{2})\s*(A1|A2|B1|B2)\s+"
    r"([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})\s+"
    r"([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(\d{1,2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(\d{1,2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(.*)$"
)

RE_YMD = re.compile(r"(\d{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日")
RE_MD  = re.compile(r"([0-9]{1,2})月\s*([0-9]{1,2})日")

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
    data/extract/bYYMMDD.txt を読む
    """
    p = os.path.join("data", "source_final_url.txt")
    if os.path.exists(p):
        try:
            url = (open(p, "r", encoding="utf-8", errors="ignore").read() or "").strip()
            m = re.search(r"/b(\d{6})\.lzh", url)
            if m:
                yymmdd = m.group(1)
                guess = os.path.join("data", "extract", f"b{yymmdd}.txt")
                if os.path.exists(guess):
                    return guess
        except Exception:
            pass

    # フォールバック：extract内のb******.txtを探す
    exdir = os.path.join("data", "extract")
    if os.path.isdir(exdir):
        cands = [fn for fn in os.listdir(exdir) if re.match(r"^b\d{6}\.txt$", fn, re.IGNORECASE)]
        if cands:
            cands.sort()
            return os.path.join(exdir, cands[-1])

    return os.path.join("data", "extract", "b260303.txt")

def split_blocks(lines: List[str]) -> List[List[str]]:
    """
    STARTB ... ENDB を1ブロックとして分割
    """
    blocks: List[List[str]] = []
    cur: List[str] = []
    in_block = False

    for raw in lines:
        l = raw.rstrip("\n")
        if "STARTB" in l:
            if cur:
                blocks.append(cur)
            cur = [l]
            in_block = True
            continue

        if in_block:
            cur.append(l)
            if "ENDB" in l:
                blocks.append(cur)
                cur = []
                in_block = False

    if cur:
        blocks.append(cur)

    # normして空行削除
    out: List[List[str]] = []
    for b in blocks:
        bb = [norm(x) for x in b if x.strip()]
        if bb:
            out.append(bb)
    return out

def parse_venue(block: List[str]) -> str:
    """
    "ボートレース大 村 3月 3日 ..." のような行から venue を復元
    "大 村" → "大村" になるようにする
    """
    for l in block[:80]:
        if "ボートレース" not in l:
            continue
        s = l.replace("ボートレース", "").strip()

        # 月が出る手前までを venue とする
        m = re.search(r"\d{1,2}月", s)
        head = s[:m.start()] if m else s

        # 空白除去して venue 完成
        v = head.replace(" ", "").strip()
        if v:
            return v
    return ""

def parse_date(block: List[str]) -> str:
    """
    年月日があればそれを優先。なければ月日+今年で補完。
    """
    for l in block[:120]:
        m = RE_YMD.search(l)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    for l in block[:160]:
        m2 = RE_MD.search(l)
        if m2:
            mo, d = m2.groups()
            y = datetime.now(JST).year
            return f"{y:04d}-{int(mo):02d}-{int(d):02d}"

    return ""

def parse_races(block: List[str]) -> List[Dict[str, Any]]:
    races: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    for l in block:
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

    return races

def classify_race(race: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    nm = race.get("name", "") or ""

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
    lines_raw = read_text_auto(txt_path)

    blocks = split_blocks(lines_raw)

    venues_out: List[Dict[str, Any]] = []
    for b in blocks:
        venue = parse_venue(b)
        ymd = parse_date(b)
        races = parse_races(b)

        # レースが取れないブロックは捨てる（ゴミ/ヘッダだけ等）
        if not venue or not races:
            continue

        for r in races:
            r["tags"] = classify_race(r)

        venues_out.append({
            "venue": venue,
            "date": ymd,
            "races": races,
        })

    # 日付は先頭 venue の日付を代表として置く
    top_date = venues_out[0]["date"] if venues_out else ""

    payload: Dict[str, Any] = {
        "source": os.path.basename(txt_path),
        "date": top_date,
        "parsed_at": datetime.now(JST).isoformat(),
        "venue_count": len(venues_out),
        "venues": venues_out,
    }

    out_path = os.path.join("data", "mbrace_races_today.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("txt:", txt_path)
    print("venues:", len(venues_out))
    if venues_out:
        print("first_venue:", venues_out[0]["venue"], "races:", len(venues_out[0]["races"]))

if __name__ == "__main__":
    main()