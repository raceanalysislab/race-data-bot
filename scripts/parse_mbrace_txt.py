# scripts/parse_mbrace_txt.py
# mbrace番組表txt（STARTB...FINALB / xxBBGN...xxBEND 想定）→ 会場ごとにパースしてJSON化
# 出力: data/mbrace_races_today.json

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

JST = timezone(timedelta(hours=9))

TRANS = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "Ｒ": "R", "Ｈ": "H", "ｍ": "m", "：": ":", "　": " ",
    "％": "%", "－": "-", "―": "-", "−": "-",
})

def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

RE_RACE_HEAD = re.compile(
    r"^\s*([0-9]{1,2})R\s+(.+?)\s+(進入固定|進入自由)?\s*H?([0-9]{3,4})m.*?締切予定\s*([0-9]{1,2}:[0-9]{2})"
)

RE_YMD = re.compile(r"(\d{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日")
RE_MD  = re.compile(r"([0-9]{1,2})月\s*([0-9]{1,2})日")

RE_BBGN = re.compile(r"\b\d{2}BBGN\b")
RE_BEND = re.compile(r"\b\d{2}BEND\b")

# ✅ 艇行の先頭（登録番号の直後はスペース無しでもOK）
RE_BOAT_PREFIX = re.compile(r"^\s*([1-6])\s+(\d{4})\s*(.*)$")

# ✅ 小数は「1〜2桁」許容（47.1 / 48.0 / 0.0 を落とさない）
FLOAT = r"[0-9]+\.[0-9]{1,2}"
FLOATP = rf"{FLOAT}%?"

# ✅ 行末の数値列（ここを後ろから確定する）
# nat_win nat_2 loc_win loc_2 motor_no motor_2 boat_no boat_2 （+残りnote）
RE_TAIL = re.compile(
    rf"({FLOATP})\s+({FLOATP})\s+"
    rf"({FLOATP})\s+({FLOATP})\s+"
    rf"(\d{{1,2}})\s+({FLOATP})\s+"
    rf"(\d{{1,2}})\s+({FLOATP})\s*(.*)$"
)

# ✅ grade の直前（スペース無しでもOK）
RE_GRADE = re.compile(r"(A1|A2|B1|B2)\s*$")

# ✅ 「年齢 支部 体重」を“後ろから”確定（スペース無しでもOK）
RE_AGE_BRANCH_WEIGHT = re.compile(r"(\d{1,2})\s*([^\d\s]{2,6})\s*(\d{2})\s*$")

def read_text_auto(path: str) -> List[str]:
    for enc in ["cp932", "utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.readlines()
        except Exception:
            pass
    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return f.readlines()

def infer_txt_path() -> str:
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

    exdir = os.path.join("data", "extract")
    if os.path.isdir(exdir):
        cands = [fn for fn in os.listdir(exdir) if re.match(r"^b\d{6}\.txt$", fn, re.IGNORECASE)]
        if cands:
            cands.sort()
            return os.path.join(exdir, cands[-1])

    return os.path.join("data", "extract", "b260303.txt")

def split_blocks(lines_raw: List[str]) -> List[List[str]]:
    blocks: List[List[str]] = []
    cur: List[str] = []
    in_block = False

    for raw in lines_raw:
        l = raw.rstrip("\n")
        if RE_BBGN.search(l):
            if cur:
                blocks.append(cur)
            cur = [l]
            in_block = True
            continue

        if in_block:
            cur.append(l)
            if RE_BEND.search(l):
                blocks.append(cur)
                cur = []
                in_block = False

    if cur:
        blocks.append(cur)

    out: List[List[str]] = []
    for b in blocks:
        bb = [norm(x) for x in b if x.strip()]
        if bb:
            out.append(bb)
    return out

def parse_venue(block: List[str]) -> str:
    for l in block[:120]:
        if "ボートレース" not in l:
            continue
        s = l.replace("ボートレース", "").strip()
        m = re.search(r"\d{1,2}月", s)
        head = s[:m.start()] if m else s
        v = head.replace(" ", "").strip()
        if v:
            return v
    return ""

def parse_date(block: List[str]) -> str:
    for l in block[:200]:
        m = RE_YMD.search(l)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    for l in block[:260]:
        m2 = RE_MD.search(l)
        if m2:
            mo, d = m2.groups()
            y = datetime.now(JST).year
            return f"{y:04d}-{int(mo):02d}-{int(d):02d}"

    return ""

def _to_float(x: str) -> Optional[float]:
    try:
        return float((x or "").replace("%", ""))
    except Exception:
        return None

def _to_int(x: str) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None

def _parse_boat_line(line: str) -> Optional[Dict[str, Any]]:
    """
    後ろ（数値列）→ grade → 年齢/支部/体重 の順に確定するので、詰め行に強い。
    """
    line = norm(line)
    mp = RE_BOAT_PREFIX.match(line)
    if not mp:
        return None

    waku = _to_int(mp.group(1))
    regno = _to_int(mp.group(2))
    rest_all = (mp.group(3) or "").strip()
    if not waku or not regno or not rest_all:
        return None

    # ① 行末の数値列を確定
    mt = RE_TAIL.search(rest_all)
    if not mt:
        return None

    nat_win = _to_float(mt.group(1))
    nat_2   = _to_float(mt.group(2))
    loc_win = _to_float(mt.group(3))
    loc_2   = _to_float(mt.group(4))
    motor_no = _to_int(mt.group(5))
    motor_2  = _to_float(mt.group(6))
    boat_no  = _to_int(mt.group(7))
    boat_2   = _to_float(mt.group(8))
    note = (mt.group(9) or "").strip()

    if None in (nat_win, nat_2, loc_win, loc_2, motor_no, motor_2, boat_no, boat_2):
        return None

    head = rest_all[:mt.start()].strip()

    # ② grade を後ろから確定
    mg = RE_GRADE.search(head)
    if not mg:
        return None
    grade = mg.group(1)
    head2 = head[:mg.start()].strip()

    # ③ 年齢/支部/体重 を後ろから確定
    mm = RE_AGE_BRANCH_WEIGHT.search(head2)
    if not mm:
        return None

    age = _to_int(mm.group(1))
    branch = mm.group(2)
    weight = _to_int(mm.group(3))
    if age is None or weight is None:
        return None

    name_raw = head2[:mm.start()].strip()
    name = (name_raw or "").replace(" ", "")
    if not name:
        return None

    return {
        "waku": int(waku),
        "regno": int(regno),
        "name": name,
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
        "note": note,
    }

def _fill_missing_waku(boats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    m = {int(b.get("waku")): b for b in boats if b.get("waku") is not None}
    out: List[Dict[str, Any]] = []
    for w in range(1, 7):
        if w in m:
            out.append(m[w])
        else:
            out.append({
                "waku": w,
                "regno": None,
                "name": "取得失敗",
                "age": None,
                "branch": "",
                "weight": None,
                "grade": "",
                "nat_win": None,
                "nat_2": None,
                "loc_win": None,
                "loc_2": None,
                "motor_no": None,
                "motor_2": None,
                "boat_no": None,
                "boat_2": None,
                "note": "WARNING: missing row (parser could not extract this boat line)",
                "_missing": True
            })
    return out

def parse_races(block: List[str]) -> List[Dict[str, Any]]:
    races: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None

    i = 0
    while i < len(block):
        l = block[i]

        mh = RE_RACE_HEAD.search(l)
        if mh:
            if cur:
                cur["boats"] = _fill_missing_waku(cur.get("boats", []))
                races.append(cur)
            cur = {
                "rno": int(mh.group(1)),
                "name": mh.group(2).strip(),
                "shinin": (mh.group(3) or "").strip(),
                "distance_m": int(mh.group(4)),
                "cutoff": mh.group(5),
                "boats": []
            }
            i += 1
            continue

        if not cur:
            i += 1
            continue

        boat = _parse_boat_line(l)

        # ✅ 行折り返し対策（次行と結合して再トライ）
        if not boat and i + 1 < len(block):
            nxt = block[i + 1]
            if (not RE_RACE_HEAD.search(nxt)) and (not RE_BOAT_PREFIX.match(nxt)):
                boat = _parse_boat_line(l + " " + nxt)
                if boat:
                    i += 1

        if boat:
            cur["boats"].append(boat)

        i += 1

    if cur:
        cur["boats"] = _fill_missing_waku(cur.get("boats", []))
        races.append(cur)

    return races

def classify_race(race: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    nm = race.get("name", "") or ""

    if any(k in nm for k in ["女子", "レディース", "ヴィーナス", "クイーン", "オールレディース"]):
        tags.append("女子戦")

    boats = race.get("boats") or []
    real_boats = [b for b in boats if not b.get("_missing")]

    if real_boats:
        b2 = sum(1 for b in real_boats if b.get("grade") == "B2")
        low = sum(1 for b in real_boats if (b.get("nat_win") or 0) <= 3.0)

        if b2 >= 2:
            tags.append("新人多め")
        if (b2 >= 2 and low >= 3) or (low >= 5):
            tags.append("荒れ注意")

        one = next((b for b in real_boats if b.get("waku") == 1), None)
        if one and (one.get("nat_win") or 0) >= 6.0:
            weak = sum(1 for b in real_boats if b.get("waku") != 1 and (b.get("nat_win") or 0) <= 4.0)
            if weak >= 4:
                tags.append("鉄板寄り")

    if any(b.get("_missing") for b in boats):
        tags.append("要確認")

    return tags

def main():
    txt_path = infer_txt_path()
    lines_raw = read_text_auto(txt_path)
    blocks = split_blocks(lines_raw)

    venues_out: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for b in blocks:
        venue = parse_venue(b)
        ymd = parse_date(b)
        races = parse_races(b)

        if not venue or not races:
            continue

        for r in races:
            r["tags"] = classify_race(r)

            boats = r.get("boats") or []
            missing = sum(1 for bb in boats if bb.get("_missing"))
            if missing:
                warnings.append(f"{venue} {r.get('rno')}R missing={missing}")

        venues_out.append({
            "venue": venue,
            "date": ymd,
            "races": races,
        })

    top_date = venues_out[0]["date"] if venues_out else ""

    payload: Dict[str, Any] = {
        "source": os.path.basename(txt_path),
        "date": top_date,
        "parsed_at": datetime.now(JST).isoformat(),
        "venue_count": len(venues_out),
        "venues": venues_out,
        "warnings": warnings,
    }

    out_path = os.path.join("data", "mbrace_races_today.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("txt:", txt_path)
    print("venues:", len(venues_out))
    if venues_out:
        print("first_venue:", venues_out[0]["venue"], "races:", len(venues_out[0]["races"]))
    if warnings:
        print("WARNINGS:")
        for w in warnings[:80]:
            print(" -", w)
        if len(warnings) > 80:
            print(" - ...", len(warnings) - 80, "more")

if __name__ == "__main__":
    main()