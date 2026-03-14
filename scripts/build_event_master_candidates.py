# scripts/build_event_master_candidates.py
# data/extract/b*.txt を走査して、開催タイトル候補を集約
# 出力:
#   data/event_master_candidates.json
#
# 目的:
# - 過去番組表から event_title / venue / total_days を一覧化
# - ここから手動で grade master / total_days master を作る

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

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
})

RE_YMD = re.compile(r"(\d{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日")
RE_MD = re.compile(r"([0-9]{1,2})月\s*([0-9]{1,2})日")
RE_BBGN = re.compile(r"\b\d{2}BBGN\b")
RE_BEND = re.compile(r"\b\d{2}BEND\b")
RE_RACE_HEAD = re.compile(
    r"^\s*([0-9]{1,2})R\s+(.+?)\s+(進入固定|進入自由)?\s*H?([0-9]{3,4})m.*?締切予定\s*([0-9]{1,2}:[0-9]{2})"
)

SG_WORDS = [
    "ボートレースクラシック",
    "ボートレースオールスター",
    "グランドチャンピオン",
    "オーシャンカップ",
    "ボートレースメモリアル",
    "ボートレースダービー",
    "チャレンジカップ",
    "グランプリシリーズ",
    "クイーンズクライマックス",
    "グランプリ",
]

G2_WORDS = [
    "レディースオールスター",
    "モーターボート誕生祭",
    "全国ボートレース甲子園",
    "レディースチャレンジカップ",
]

G1_WORDS = [
    "地区選手権",
    "ダイヤモンドカップ",
    "モーターボート大賞",
]

G3_WORDS = [
    "オールレディース",
    "企業杯",
    "イースタンヤング",
    "ウエスタンヤング",
    "マスターズリーグ",
    "シャボン玉石けん杯",
]

G1_EXACT_WORDS = [
    "地区選手権",
    "ダイヤモンドカップ",
    "モーターボート大賞",
    "BBCトーナメント",
    "センプルカップ",
    "キングカップ",
    "海の王者決定戦",
]

RE_G1_ANNIV_HEAD = re.compile(r"^開設\d+周年記念")
RE_G1_CITY_ANNIV = re.compile(r"[^\s]*市制\d+周年記念")
RE_G1_DISTRICT = re.compile(r"地区選手権")
RE_G3_COMPANY = re.compile(r"企業杯")
RE_G3_LADIES = re.compile(r"オールレディース")
RE_G3_YOUNG = re.compile(r"(イースタンヤング|ウエスタンヤング)")
RE_G3_MASTERS = re.compile(r"マスターズリーグ")

NOISE_PATTERNS = [
    r"^艇選手選手年支体級",
    r"^艇選手選手",
    r"^選手登番",
    r"^今節成績",
    r"^モーター",
    r"^ボート",
    r"^電話投票締切予定",
    r"^内容については主催者発行のものと照合して下さい$",
    r"^\*{3}番組表\*{3}$",
    r"^-+$",
]
NOISE_RES = [re.compile(p) for p in NOISE_PATTERNS]


def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def compact(s: str) -> str:
    return norm(s).replace(" ", "")


COMPACT_SG_WORDS = [compact(w) for w in SG_WORDS]
COMPACT_G2_WORDS = [compact(w) for w in G2_WORDS]
COMPACT_G1_WORDS = [compact(w) for w in G1_WORDS]
COMPACT_G3_WORDS = [compact(w) for w in G3_WORDS]
COMPACT_G1_EXACT_WORDS = [compact(w) for w in G1_EXACT_WORDS]


def _contains_any(raw: str, words: List[str]) -> bool:
    return any(w in raw for w in words)


def _looks_like_g1_anniversary(raw: str) -> bool:
    if RE_G1_ANNIV_HEAD.match(raw):
        return True
    if RE_G1_CITY_ANNIV.search(raw):
        return True
    if _contains_any(raw, COMPACT_G1_EXACT_WORDS):
        return True
    return False


def detect_grade_from_title(title: str) -> str:
    raw = compact(title)
    upper = raw.upper()

    if not raw:
        return "一般"

    if re.search(r"(^|[^A-Z])SG([^A-Z]|$)", upper):
        return "SG"
    if re.search(r"(^|[^A-Z])(G1|GI)([^A-Z]|$)", upper):
        return "G1"
    if re.search(r"(^|[^A-Z])(G2|GII)([^A-Z]|$)", upper):
        return "G2"
    if re.search(r"(^|[^A-Z])(G3|GIII)([^A-Z]|$)", upper):
        return "G3"

    if _contains_any(raw, COMPACT_SG_WORDS):
        return "SG"
    if _contains_any(raw, COMPACT_G2_WORDS):
        return "G2"

    if RE_G1_DISTRICT.search(raw):
        return "G1"
    if _looks_like_g1_anniversary(raw):
        return "G1"

    if RE_G3_LADIES.search(raw):
        return "G3"
    if RE_G3_COMPANY.search(raw):
        return "G3"
    if RE_G3_YOUNG.search(raw):
        return "G3"
    if RE_G3_MASTERS.search(raw):
        return "G3"

    if _contains_any(raw, COMPACT_G1_WORDS):
        return "G1"
    if _contains_any(raw, COMPACT_G3_WORDS):
        return "G3"

    return "一般"


def read_text_auto(path: str) -> List[str]:
    for enc in ["cp932", "utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.readlines()
        except Exception:
            pass
    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return f.readlines()


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


def is_noise_title(cand: str) -> bool:
    n = compact(cand)
    if not n:
        return True

    if RE_RACE_HEAD.search(norm(cand)):
        return True

    for rx in NOISE_RES:
        if rx.search(n):
            return True

    if "締切予定" in n:
        return True
    if "ボートレース" in n:
        return True
    if "主催者発行" in n:
        return True
    if "内容については主催者発行のものと照合して下さい" in n:
        return True
    if "艇選手選手" in n:
        return True
    if "今節成績" in n:
        return True

    return False


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
            if is_noise_title(cand):
                continue
            return cand.strip()

    for line in cleaned[:12]:
        if "ボートレース" not in line:
            continue

        s = norm(line)
        m = re.search(r"\d{1,2}月\s*\d{1,2}日\s+(.*?)\s+第\s*[0-9]+\s*日", s)
        if m:
            title = norm(m.group(1))
            if title and not is_noise_title(title):
                return title

    return ""


def title_key(title: str) -> str:
    return norm(title)


def collect_from_file(path: str) -> List[Dict]:
    lines_raw = read_text_auto(path)
    blocks = split_blocks(lines_raw)

    rows: List[Dict] = []
    for b in blocks:
        venue = parse_venue(b)
        date = parse_date(b)
        event_title = parse_event_title(b)
        current_day, total_days = parse_day_info(b)
        day_label = format_day_label(current_day, total_days)

        if not venue or not event_title:
            continue

        rows.append({
            "source_file": os.path.basename(path),
            "venue": venue,
            "date": date,
            "event_title": event_title,
            "title_key": title_key(event_title),
            "day": current_day,
            "total_days": total_days,
            "day_label": day_label,
        })
    return rows


def main():
    extract_dir = os.path.join("data", "extract")
    if not os.path.isdir(extract_dir):
        raise FileNotFoundError(f"extract dir not found: {extract_dir}")

    txt_files = [
        os.path.join(extract_dir, fn)
        for fn in os.listdir(extract_dir)
        if re.match(r"^b\d{6}\.txt$", fn, re.IGNORECASE)
    ]
    txt_files.sort()

    all_rows: List[Dict] = []
    errors: List[Dict] = []

    for path in txt_files:
        try:
            all_rows.extend(collect_from_file(path))
        except Exception as e:
            errors.append({
                "source_file": os.path.basename(path),
                "error": str(e),
            })

    by_title: Dict[str, List[Dict]] = defaultdict(list)
    for row in all_rows:
        key = row["title_key"]
        by_title[key].append(row)

    titles_out: List[Dict] = []

    for key, rows in sorted(by_title.items(), key=lambda x: x[0]):
        venues = sorted({r["venue"] for r in rows if r.get("venue")})
        total_days_values = sorted({r["total_days"] for r in rows if r.get("total_days") is not None})
        sample_titles = sorted({r["event_title"] for r in rows if r.get("event_title")})
        sample_files = sorted({r["source_file"] for r in rows if r.get("source_file")})[:20]
        sample_dates = sorted({r["date"] for r in rows if r.get("date")})[:20]

        auto_grade = detect_grade_from_title(key)
        confirmed_total_days = total_days_values[0] if len(total_days_values) == 1 else None

        titles_out.append({
            "title_key": key,
            "sample_titles": sample_titles[:10],
            "venues": venues,
            "total_days_candidates": total_days_values,
            "occurrences": len(rows),
            "sample_files": sample_files,
            "sample_dates": sample_dates,
            "grade_label": auto_grade,
            "confirmed_total_days": confirmed_total_days,
            "notes": "",
        })

    payload = {
        "generated_at": datetime.now(JST).isoformat(),
        "source_dir": extract_dir,
        "source_file_count": len(txt_files),
        "title_count": len(titles_out),
        "titles": titles_out,
        "errors": errors,
    }

    out_path = os.path.join("data", "event_master_candidates.json")
    os.makedirs("data", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("source_file_count:", len(txt_files))
    print("title_count:", len(titles_out))
    print("out:", out_path)
    if errors:
        print("errors:", len(errors))


if __name__ == "__main__":
    main()