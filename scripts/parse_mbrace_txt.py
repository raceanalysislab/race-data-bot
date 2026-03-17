# scripts/parse_mbrace_txt.py
# mbrace番組表txt（STARTB...FINALB / xxBBGN...xxBEND 想定）→ 会場ごとにパースしてJSON化
# 出力:
#   data/mbrace_races_YYYY-MM-DD.json
# today / tomorrow 方式は廃止し、日付ファイル方式に統一

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

TRANS = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "Ｒ": "R", "Ｈ": "H", "ｍ": "m", "：": ":", "　": " ",
    "％": "%", "－": "-", "―": "-", "−": "-",
    "Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III",
    "ａ": "a", "ｂ": "b", "ｃ": "c", "ｄ": "d", "ｅ": "e",
    "ｆ": "f", "ｇ": "g", "ｈ": "h", "ｉ": "i", "ｊ": "j",
    "ｋ": "k", "ｌ": "l", "ｍ": "m", "ｎ": "n", "ｏ": "o",
    "ｐ": "p", "ｑ": "q", "ｒ": "r", "ｓ": "s", "ｔ": "t",
    "ｕ": "u", "ｖ": "v", "ｗ": "w", "ｘ": "x", "ｙ": "y",
    "ｚ": "z",
    "Ａ": "A", "Ｂ": "B", "Ｃ": "C", "Ｄ": "D", "Ｅ": "E",
    "Ｆ": "F", "Ｇ": "G", "Ｈ": "H", "Ｉ": "I", "Ｊ": "J",
    "Ｋ": "K", "Ｌ": "L", "Ｍ": "M", "Ｎ": "N", "Ｏ": "O",
    "Ｐ": "P", "Ｑ": "Q", "Ｒ": "R", "Ｓ": "S", "Ｔ": "T",
    "Ｕ": "U", "Ｖ": "V", "Ｗ": "W", "Ｘ": "X", "Ｙ": "Y",
    "Ｚ": "Z",
    "（": "(", "）": ")",
})

BRANCHES = [
    "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島",
    "茨城", "栃木", "群馬", "埼玉", "千葉", "東京", "神奈川",
    "新潟", "富山", "石川", "福井", "山梨", "長野",
    "岐阜", "静岡", "愛知", "三重",
    "滋賀", "京都", "大阪", "兵庫", "奈良", "和歌山",
    "鳥取", "島根", "岡山", "広島", "山口",
    "徳島", "香川", "愛媛", "高知",
    "福岡", "佐賀", "長崎", "熊本", "大分", "宮崎", "鹿児島", "沖縄",
]
VENUE_NAMES = [
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑",
    "津", "三国", "びわこ", "住之江", "尼崎", "鳴門", "丸亀", "児島",
    "宮島", "徳山", "下関", "若松", "芦屋", "福岡", "唐津", "大村"
]

BRANCH_PATTERN = "|".join(sorted(map(re.escape, BRANCHES), key=len, reverse=True))

RE_RACE_HEAD = re.compile(
    r"^\s*([0-9]{1,2})R\s+(.+?)\s+(進入固定|進入自由)?\s*H?([0-9]{3,4})m.*?締切予定\s*([0-9]{1,2}:[0-9]{2})"
)
RE_YMD = re.compile(r"(\d{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日")
RE_MD = re.compile(r"([0-9]{1,2})月\s*([0-9]{1,2})日")
RE_BBGN = re.compile(r"\b\d{2}BBGN\b")
RE_BEND = re.compile(r"\b\d{2}BEND\b")
RE_BOAT_PREFIX = re.compile(r"^\s*([1-6])\s+(\d{4})\s*(.*)$")

EVENT_MASTER_PATH = os.path.join("data", "event_master.json")


def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def compact(s: str) -> str:
    return norm(s).replace(" ", "")


def _dedupe_venue_prefix(s: str) -> str:
    s = s.strip()

    # 例: "尼崎 尼崎センプルカップ" -> "尼崎センプルカップ"
    for v in VENUE_NAMES:
        prefix = f"{v} "
        if s.startswith(prefix) and s[len(prefix):].startswith(v):
            return s[len(prefix):].strip()

    # 例: "尼崎 尼崎 ..." 以外にも、前半と後半の頭が同じ会場なら吸収
    m = re.match(r"^(" + "|".join(map(re.escape, VENUE_NAMES)) + r")\s+\1(.*)$", s)
    if m:
        return f"{m.group(1)}{m.group(2)}".strip()

    return s


def normalize_event_title(s: str) -> str:
    s = norm(s)

    # グレード表記は照合ノイズ
    s = re.sub(r"\bSG\b", "", s)
    s = re.sub(r"\bG[123]\b", "", s)

    # 回数は年で変わる
    s = re.sub(r"第\s*\d+\s*回", "", s)

    # 周年系は年で変わる
    s = re.sub(r"市制\s*\d+\s*周年記念", "", s)
    s = re.sub(r"創刊\s*\d+\s*周年記念", "", s)
    s = re.sub(r"開設\s*\d+\s*周年記念競走", "", s)
    s = re.sub(r"開設\s*\d+\s*周年記念", "", s)
    s = re.sub(r"\d+\s*周年記念", "", s)
    s = re.sub(r"\d+\s*周年", "", s)

    # 開設記念系の表記ゆれ吸収
    s = re.sub(r"\(\s*開設記念\s*\)", "", s)
    s = re.sub(r"開設記念競走", "", s)
    s = re.sub(r"開設記念", "", s)

    # 記念だけ単独で残ったら消す
    s = re.sub(r"\b記念\b", "", s)

    # 記号/空白整理
    s = re.sub(r"[()]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # 会場名重複吸収
    s = _dedupe_venue_prefix(s)

    # もう一度整形
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compact_event_title(s: str) -> str:
    return normalize_event_title(s).replace(" ", "")


def load_event_master() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(EVENT_MASTER_PATH):
        return {}

    try:
        with open(EVENT_MASTER_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}

    if isinstance(raw, dict) and isinstance(raw.get("events"), dict):
        raw_events = raw.get("events") or {}
    elif isinstance(raw, dict):
        raw_events = raw
    else:
        return {}

    out: Dict[str, Dict[str, Any]] = {}

    for k, v in raw_events.items():
        key_norm = normalize_event_title(str(k))
        key_compact = compact_event_title(str(k))
        if not key_norm or not key_compact:
            continue

        if isinstance(v, dict):
            grade = str(v.get("grade") or "一般").strip() or "一般"
            total_days = v.get("total_days")
            notes = str(v.get("notes") or "").strip()
            sample_titles = v.get("sample_titles") if isinstance(v.get("sample_titles"), list) else []
            venues = v.get("venues") if isinstance(v.get("venues"), list) else []
        else:
            grade = "一般"
            total_days = None
            notes = ""
            sample_titles = []
            venues = []

        try:
            total_days = int(total_days) if total_days is not None else None
        except Exception:
            total_days = None

        out[key_compact] = {
            "title": key_norm,
            "grade": grade,
            "total_days": total_days,
            "notes": notes,
            "sample_titles": sample_titles,
            "venues": venues,
        }

    return out


EVENT_MASTER = load_event_master()


def lookup_event_master(title: str) -> Optional[Dict[str, Any]]:
    t_compact = compact_event_title(title)
    if not t_compact:
        return None
    return EVENT_MASTER.get(t_compact)


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

    for raw in lines_raw:
        l = raw.rstrip("\n")

        if RE_BBGN.search(l):
            if cur:
                blocks.append(cur)
            cur = [l]
            continue

        cur.append(l)

        if RE_BEND.search(l):
            blocks.append(cur)
            cur = []

    if cur:
        blocks.append(cur)

    out: List[List[str]] = []
    for b in blocks:
        bb = [norm(x) for x in b if x.strip()]
        if bb:
            out.append(bb)
    return out


def parse_venue(block: List[str]) -> str:
    for l in block[:200]:
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
    for l in block[:300]:
        m = RE_YMD.search(l)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    for l in block[:340]:
        m2 = RE_MD.search(l)
        if m2:
            mo, d = m2.groups()
            y = datetime.now(JST).year
            return f"{y:04d}-{int(mo):02d}-{int(d):02d}"

    return ""


def parse_day_info(block: List[str]) -> Tuple[Optional[int], Optional[int]]:
    current_day: Optional[int] = None
    total_days: Optional[int] = None

    joined = "\n".join(block[:160])
    c = compact(joined)

    m = re.search(r"第([0-9]+)日", c)
    if m:
        try:
            current_day = int(m.group(1))
        except Exception:
            pass

    if current_day is None:
        m = re.search(r"([0-9]+)日目", c)
        if m:
            try:
                current_day = int(m.group(1))
            except Exception:
                pass

    m = re.search(r"([0-9]+)日間", c)
    if m:
        try:
            total_days = int(m.group(1))
        except Exception:
            pass

    if current_day is None or total_days is None:
        m = re.search(r"([0-9]+)\/([0-9]+)", c)
        if m:
            try:
                if current_day is None:
                    current_day = int(m.group(1))
                if total_days is None:
                    total_days = int(m.group(2))
            except Exception:
                pass

    return current_day, total_days


def format_day_label(current_day: Optional[int], total_days: Optional[int]) -> Optional[str]:
    if current_day is None:
        return None
    if current_day == 1:
        return "初日"
    if total_days is not None and current_day == total_days:
        return "最終日"
    return f"{current_day}日目"


def parse_event_title(block: List[str]) -> str:
    cleaned = [norm(x) for x in block if norm(x)]
    if not cleaned:
        return ""

    for i, line in enumerate(cleaned[:80]):
        c = compact(line)
        if "番組表" not in c:
            continue

        for j in range(i + 1, min(i + 8, len(cleaned))):
            cand = norm(cleaned[j])
            cc = compact(cand)
            if not cc:
                continue

            if "ボートレース" in cc:
                continue
            if "主催者発行" in cc:
                continue
            if "内容については主催者発行のものと照合して下さい" in cc:
                continue
            if re.search(r"第[0-9]+日", cc) and re.search(r"[0-9]{4}年", cc):
                continue
            if RE_RACE_HEAD.search(cand):
                continue
            if cc.startswith("----"):
                continue
            if "締切予定" in cc:
                continue

            return cand.strip()

    for line in cleaned[:12]:
        if "ボートレース" not in line:
            continue

        s = norm(line)
        m = re.search(r"\d{1,2}月\s*\d{1,2}日\s+(.*?)\s+第\s*[0-9]+\s*日", s)
        if m:
            title = norm(m.group(1))
            if title:
                return title

    return ""


def resolve_grade(title: str) -> str:
    master_hit = lookup_event_master(title)
    if master_hit:
        grade = str(master_hit.get("grade") or "").strip()
        if grade:
            return grade
    return "一般"


def resolve_total_days(event_title: str, parsed_total_days: Optional[int]) -> Optional[int]:
    if parsed_total_days is not None:
        return parsed_total_days

    master_hit = lookup_event_master(event_title)
    if master_hit:
        td = master_hit.get("total_days")
        try:
            return int(td) if td is not None else None
        except Exception:
            return None

    return None


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


def _normalize_boat_line(s: str) -> str:
    return norm(s)


def _build_boat_dict(
    *,
    waku: int,
    regno: int,
    name: str,
    age: int,
    branch: str,
    weight: int,
    grade: str,
    nat_win: float,
    nat_2: float,
    loc_win: float,
    loc_2: float,
    motor_no: int,
    motor_2: float,
    boat_no: int,
    boat_2: float,
    note: str,
) -> Dict[str, Any]:
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


def _parse_stats_tail(tail: str) -> Optional[Tuple[float, float, float, float, int, float, int, float, str]]:
    s = _normalize_boat_line(tail)

    m4 = re.match(
        r"^\s*"
        r"([0-9]+\.[0-9]{1,2})\s+"
        r"([0-9]+\.[0-9]{1,2})\s+"
        r"([0-9]+\.[0-9]{1,2})\s+"
        r"([0-9]+\.[0-9]{1,2})\s+"
        r"(.*)$",
        s,
    )
    if not m4:
        return None

    nat_win = _to_float(m4.group(1))
    nat_2 = _to_float(m4.group(2))
    loc_win = _to_float(m4.group(3))
    loc_2 = _to_float(m4.group(4))
    rest = m4.group(5).strip()

    if None in (nat_win, nat_2, loc_win, loc_2):
        return None

    m_tail = re.match(
        r"^\s*"
        r"(\d{1,3})\s*"
        r"(\d{1,3}\.\d{2})\s*"
        r"(\d{1,3})\s+"
        r"([0-9]+\.[0-9]{1,2})"
        r"(?:\s+(.*))?$",
        rest,
    )
    if not m_tail:
        return None

    motor_no = _to_int(m_tail.group(1))
    motor_2 = _to_float(m_tail.group(2))
    boat_no = _to_int(m_tail.group(3))
    boat_2 = _to_float(m_tail.group(4))
    note = norm(m_tail.group(5) or "")

    if None in (motor_no, motor_2, boat_no, boat_2):
        return None

    if motor_no < 1 or boat_no < 1:
        return None
    if not (0.0 <= motor_2 <= 100.0 and 0.0 <= boat_2 <= 100.0):
        return None

    return (
        float(nat_win),
        float(nat_2),
        float(loc_win),
        float(loc_2),
        int(motor_no),
        float(motor_2),
        int(boat_no),
        float(boat_2),
        note,
    )


def _parse_boat_line_main(line: str) -> Optional[Dict[str, Any]]:
    line = _normalize_boat_line(line)

    mp = RE_BOAT_PREFIX.match(line)
    if not mp:
        return None

    waku = _to_int(mp.group(1))
    regno = _to_int(mp.group(2))
    rest_all = (mp.group(3) or "").strip()

    if not waku or not regno or not rest_all:
        return None

    mg = re.search(r"(A1|A2|B1|B2)\s+", rest_all)
    if not mg:
        mg = re.search(r"(A1|A2|B1|B2)", rest_all)
        if not mg:
            return None

    grade = mg.group(1)
    head = rest_all[:mg.start()].strip()
    tail = rest_all[mg.end():].strip()

    mh = re.search(rf"(.+?)(\d{{1,2}})({BRANCH_PATTERN})(\d{{2}})$", head)
    if not mh:
        return None

    name = re.sub(r"\s+", "", mh.group(1) or "")
    age = _to_int(mh.group(2))
    branch = mh.group(3)
    weight = _to_int(mh.group(4))

    if not name or age is None or weight is None:
        return None

    parsed_tail = _parse_stats_tail(tail)
    if not parsed_tail:
        return None

    nat_win, nat_2, loc_win, loc_2, motor_no, motor_2, boat_no, boat_2, note = parsed_tail

    return _build_boat_dict(
        waku=int(waku),
        regno=int(regno),
        name=name,
        age=int(age),
        branch=branch,
        weight=int(weight),
        grade=grade,
        nat_win=float(nat_win),
        nat_2=float(nat_2),
        loc_win=float(loc_win),
        loc_2=float(loc_2),
        motor_no=int(motor_no),
        motor_2=float(motor_2),
        boat_no=int(boat_no),
        boat_2=float(boat_2),
        note=note,
    )


def _parse_boat_line(line: str) -> Optional[Dict[str, Any]]:
    return _parse_boat_line_main(line)


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


def _is_boat_candidate(line: str) -> bool:
    s = _normalize_boat_line(line)
    return bool(RE_BOAT_PREFIX.match(s))


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

        boat = None
        if _is_boat_candidate(l):
            boat = _parse_boat_line(l)

            if not boat and i + 1 < len(block):
                nxt = block[i + 1]
                nxt_norm = _normalize_boat_line(nxt)
                if not RE_RACE_HEAD.search(nxt_norm) and not _is_boat_candidate(nxt_norm):
                    boat = _parse_boat_line(f"{l} {nxt}")
                    if boat:
                        i += 1

            if not boat and i + 2 < len(block):
                nxt1 = block[i + 1]
                nxt2 = block[i + 2]
                nxt1_norm = _normalize_boat_line(nxt1)
                nxt2_norm = _normalize_boat_line(nxt2)
                if (
                    not RE_RACE_HEAD.search(nxt1_norm) and
                    not RE_RACE_HEAD.search(nxt2_norm) and
                    not _is_boat_candidate(nxt1_norm) and
                    not _is_boat_candidate(nxt2_norm)
                ):
                    boat = _parse_boat_line(f"{l} {nxt1} {nxt2}")
                    if boat:
                        i += 2

            if not boat and i + 3 < len(block):
                nxt1 = block[i + 1]
                nxt2 = block[i + 2]
                nxt3 = block[i + 3]
                nxt1_norm = _normalize_boat_line(nxt1)
                nxt2_norm = _normalize_boat_line(nxt2)
                nxt3_norm = _normalize_boat_line(nxt3)
                if (
                    not RE_RACE_HEAD.search(nxt1_norm) and
                    not RE_RACE_HEAD.search(nxt2_norm) and
                    not RE_RACE_HEAD.search(nxt3_norm) and
                    not _is_boat_candidate(nxt1_norm) and
                    not _is_boat_candidate(nxt2_norm) and
                    not _is_boat_candidate(nxt3_norm)
                ):
                    boat = _parse_boat_line(f"{l} {nxt1} {nxt2} {nxt3}")
                    if boat:
                        i += 3

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


def build_output_path(date_str: str) -> str:
    safe_date = date_str if date_str else "unknown"
    return os.path.join("data", f"mbrace_races_{safe_date}.json")


def cleanup_old_outputs(current_out_path: str) -> None:
    if not os.path.isdir("data"):
        return

    for name in os.listdir("data"):
        if not re.match(r"^mbrace_races_(\d{4}-\d{2}-\d{2})\.json$", name):
            continue

        path = os.path.join("data", name)
        if os.path.abspath(path) == os.path.abspath(current_out_path):
            continue

        try:
            os.remove(path)
        except Exception:
            pass


def main():
    txt_path = infer_txt_path()
    lines_raw = read_text_auto(txt_path)
    blocks = split_blocks(lines_raw)

    venues_out: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for b in blocks:
        venue = parse_venue(b)
        ymd = parse_date(b)
        current_day, parsed_total_days = parse_day_info(b)
        event_title = parse_event_title(b)
        event_title_norm = normalize_event_title(event_title)
        total_days = resolve_total_days(event_title, parsed_total_days)
        day_label = format_day_label(current_day, total_days)
        grade_label = resolve_grade(event_title)
        races = parse_races(b)

        if not venue or not races:
            continue

        for r in races:
            r["tags"] = classify_race(r)
            missing = sum(1 for bb in (r.get("boats") or []) if bb.get("_missing"))
            if missing:
                warnings.append(f"{venue} {r.get('rno')}R missing={missing} race_name={r.get('name')}")

        venue_payload: Dict[str, Any] = {
            "venue": venue,
            "date": ymd,
            "event_title": event_title,
            "event_title_norm": event_title_norm,
            "grade_label": grade_label,
        }
        if current_day is not None:
            venue_payload["day"] = current_day
        if total_days is not None:
            venue_payload["total_days"] = total_days
        if day_label is not None:
            venue_payload["day_label"] = day_label
        venue_payload["races"] = races

        venues_out.append(venue_payload)

    top_date = venues_out[0]["date"] if venues_out else ""
    out_path = build_output_path(top_date)

    payload: Dict[str, Any] = {
        "source": os.path.basename(txt_path),
        "date": top_date,
        "parsed_at": datetime.now(JST).isoformat(),
        "venue_count": len(venues_out),
        "venues": venues_out,
        "warnings": warnings,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    cleanup_old_outputs(out_path)

    print("txt:", txt_path)
    print("out:", out_path)
    print("venues:", len(venues_out))
    print("event_master_loaded:", len(EVENT_MASTER))
    if venues_out:
        print(
            "first_venue:",
            venues_out[0]["venue"],
            "day:",
            venues_out[0].get("day"),
            "label:",
            venues_out[0].get("day_label"),
            "grade:",
            venues_out[0].get("grade_label"),
            "title:",
            venues_out[0].get("event_title"),
            "title_norm:",
            venues_out[0].get("event_title_norm"),
        )
        print("first_venue_races:", len(venues_out[0]["races"]))
    if warnings:
        print("WARNINGS:")
        for w in warnings[:120]:
            print(" -", w)
        if len(warnings) > 120:
            print(" - ...", len(warnings) - 120, "more")


if __name__ == "__main__":
    main()