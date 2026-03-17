# scripts/build_meet_avg_st_from_k.py
# extract_k 内の k******.txt を全部読んで
# 同一開催（会場 + 開催タイトル）の日付ごとの
# 選手別「今節ここまで平均ST」を作る
#
# 出力:
#   data/meet_avg_st/<会場>_<日付>.json
#
# 重要:
# - 内部では 会場 + 日付 ごとに最終出力を作る
# - 会場名は必ず正規化して「三　国」→「三国」のように揃える
# - イベントタイトルは保持するが、会場名ズレでは落ちないようにする
# - ST は「展示タイム」「進入」の後ろにある値だけを拾う
# - K0 は平均STの対象外
# - F / L は平均STの対象外
# - 未一致行はログ出力して追跡できるようにする
# - 出力前に data/meet_avg_st 配下の既存jsonを全削除して、古いゴミファイルを残さない
# - 年は k230315.txt → 2023-03-15 のように、まずファイル名から確定する

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

RE_KBGN = re.compile(r"^\d{2}KBGN$")
RE_KEND = re.compile(r"^\d{2}KEND$")
RE_DATE = re.compile(r"(\d{1,2})/(\d{1,2})")
RE_RACE_HEADER = re.compile(r"^\s*(\d{1,2})R")
RE_K_FILENAME = re.compile(r"^k(\d{2})(\d{2})(\d{2})\.txt$", re.IGNORECASE)

# 行頭の基本情報だけ先に取る
RE_RESULT_ROW_HEAD = re.compile(
    r"^\s*([0-9]{2}|S[0-9]|F|K0)\s+([1-6])\s+(\d{4})\s+(.+)$"
)

RE_RESULT_ROW_CANDIDATE = re.compile(
    r"^([0-9]{2}|S[0-9]|F|K0)\s+[1-6]\s+\d{4}\s+"
)


def norm_space(s: str) -> str:
    s = (s or "").replace("\u3000", " ")
    return re.sub(r"\s+", " ", s).strip()


def safe_filename_part(s: str) -> str:
    s = norm_space(s)
    for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
        s = s.replace(ch, "_")
    return s


def normalize_venue(s: str) -> str:
    s = s or ""
    s = s.replace("ボートレース", "")
    s = s.replace("\u3000", "")
    s = s.replace(" ", "")
    return s.strip()


def normalize_event_title(s: str) -> str:
    s = norm_space(s)
    s = s.replace("　", " ")
    s = re.sub(r"\s+", " ", s)
    s = s.replace("第４７回", "第47回")
    s = s.replace("第４８回", "第48回")
    s = s.replace("第１１th", "第11th")
    s = s.replace("１１th", "11th")
    s = s.replace("　", "")
    s = s.replace(" ", "")
    return s


def read_text_auto(path: str) -> List[str]:
    for enc in ["cp932", "utf-8-sig", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return [x.rstrip("\n") for x in f]
        except Exception:
            pass
    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return [x.rstrip("\n") for x in f]


def split_blocks(lines: List[str]) -> List[List[str]]:
    blocks: List[List[str]] = []
    cur: List[str] = []

    for line in lines:
        if RE_KBGN.match(line.strip()):
            if cur:
                blocks.append(cur)
            cur = [line]
            continue

        cur.append(line)

        if RE_KEND.match(line.strip()):
            blocks.append(cur)
            cur = []

    if cur:
        blocks.append(cur)

    return [b for b in blocks if b]


def parse_venue(block: List[str]) -> str:
    for line in block[:8]:
        s = norm_space(line)
        if "［成績］" in s:
            raw = s.split("［成績］", 1)[0]
            return normalize_venue(raw)
    return ""


def infer_year_from_path(path: str) -> int:
    name = os.path.basename(path)
    m = RE_K_FILENAME.match(name)
    if m:
        yy = int(m.group(1))
        return 1900 + yy if yy >= 90 else 2000 + yy
    return datetime.now(JST).year


def parse_date(block: List[str], path: str) -> str:
    year = infer_year_from_path(path)

    for line in block[:30]:
        m = RE_DATE.search(line)
        if m:
            mm, dd = m.groups()
            return f"{year:04d}-{int(mm):02d}-{int(dd):02d}"

    return ""


def parse_event_title(block: List[str]) -> str:
    for idx, line in enumerate(block):
        s = norm_space(line)

        if "競走成績" in s:
            for j in range(idx + 1, min(idx + 8, len(block))):
                t = norm_space(block[j])

                if not t:
                    continue
                if "第 " in t and "日" in t:
                    continue
                if re.search(r"\d{4}/\s*\d{1,2}/\d{1,2}", t):
                    continue
                if "ボートレース" in t and len(t) <= 12:
                    continue
                if "内容については主催者発行のものと照合して下さい" in t:
                    continue
                if "払戻金" in t:
                    continue

                return t

    for line in block[:8]:
        s = norm_space(line)
        if "［成績］" in s:
            m = re.search(r"［成績］\s+\d{1,2}/\d{1,2}\s+(.+?)\s+第\s*\d+日", s)
            if m:
                return norm_space(m.group(1))

    return ""


def list_k_txt_files() -> List[str]:
    candidates: List[str] = []
    search_dirs = [
        os.path.join("data", "extract_k"),
        os.path.join("data", "extract"),
        os.path.join("data"),
    ]

    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for fn in files:
                if re.match(r"^k\d{6}\.txt$", fn, re.IGNORECASE):
                    candidates.append(os.path.join(root, fn))

    return sorted(set(candidates))


def extract_name_from_tail(tail: str) -> str:
    # 名前はモーター番号の直前までを取る
    m = re.match(r"(.+?)\s+\d+\s+\d+\s+", tail)
    if m:
        return norm_space(m.group(1))
    return norm_space(tail)


def extract_st_from_result_line(line: str) -> Tuple[Optional[float], bool, bool]:
    """
    結果行から ST を抽出する。
    戻り値:
      (st, is_f, is_l)

    想定並び:
      ... モーター ボート 展示(6.81) 進入(3) ST(0.19 or F0.02 or L0.12) ...
    """

    s = line.rstrip()

    # K0行は今節平均STの対象外
    if re.match(r"^\s*K0\s+", s):
        return None, False, False

    m = re.search(
        r"\s+\d+\s+\d+\s+(\d+\.\d{2})\s+([1-6])\s+([FL]?\d+\.\d{2})\b",
        s
    )
    if not m:
        return None, False, False

    st_raw = m.group(3).strip()
    is_f = st_raw.startswith("F")
    is_l = st_raw.startswith("L")

    st_num = st_raw.lstrip("F").lstrip("L")

    try:
        return float(st_num), is_f, is_l
    except Exception:
        return None, is_f, is_l


def clear_output_dir(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for fn in os.listdir(out_dir):
        path = os.path.join(out_dir, fn)
        if os.path.isfile(path) and fn.lower().endswith(".json"):
            os.remove(path)


def main() -> None:
    paths = list_k_txt_files()
    if not paths:
        raise FileNotFoundError("k結果txtが見つかりません。data/extract_k を確認してください。")

    # venue|event_title_norm -> date -> reg -> stats
    day_stats: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(
                lambda: {"st_sum": 0.0, "st_count": 0, "name": ""}
            )
        )
    )

    # meet key meta
    meet_meta: Dict[str, Dict[str, str]] = {}

    file_count = 0
    race_count = 0
    unmatched_rows = 0
    skipped_k0_rows = 0
    skipped_f_rows = 0
    skipped_l_rows = 0

    for path in paths:
        lines = read_text_auto(path)
        blocks = split_blocks(lines)
        file_count += 1

        for block in blocks:
            venue = parse_venue(block)
            date_str = parse_date(block, path)
            event_title_raw = parse_event_title(block)

            if not venue or not event_title_raw or not date_str:
                continue

            event_title_norm = normalize_event_title(event_title_raw)
            meet_key = f"{venue}|{event_title_norm}"

            if meet_key not in meet_meta:
                meet_meta[meet_key] = {
                    "venue": venue,
                    "event_title": event_title_raw,
                    "event_title_norm": event_title_norm,
                }

            current_race = None
            in_result_table = False

            for line in block:
                race_head = RE_RACE_HEADER.match(line)
                if race_head and "H1800m" in line:
                    current_race = int(race_head.group(1))
                    in_result_table = False
                    race_count += 1
                    continue

                if current_race is None:
                    continue

                if "着 艇 登番" in line:
                    in_result_table = True
                    continue

                if in_result_table:
                    head = RE_RESULT_ROW_HEAD.match(line)
                    if head:
                        rank = str(head.group(1)).strip()
                        reg = str(head.group(3)).strip()
                        tail = str(head.group(4))
                        name = extract_name_from_tail(tail)

                        if rank == "K0":
                            skipped_k0_rows += 1
                            continue

                        st, is_f, is_l = extract_st_from_result_line(line)

                        if is_f:
                            skipped_f_rows += 1
                            continue

                        if is_l:
                            skipped_l_rows += 1
                            continue

                        if reg and st is not None:
                            day_stats[meet_key][date_str][reg]["st_sum"] += st
                            day_stats[meet_key][date_str][reg]["st_count"] += 1
                            if name:
                                day_stats[meet_key][date_str][reg]["name"] = name
                            continue

                        s = line.strip()
                        if s and RE_RESULT_ROW_CANDIDATE.match(s):
                            unmatched_rows += 1
                            print("UNMATCHED_RESULT_ROW:", s)
                        continue

                    if (
                        line.strip() == ""
                        or line.strip().startswith("単勝")
                        or "レース不成立" in line
                        or "払戻金" in line
                    ):
                        in_result_table = False

    # 会場+日付ごとにマージ出力
    merged_outputs: Dict[str, Dict[str, Any]] = {}

    for meet_key, dated_regs in day_stats.items():
        dates_sorted = sorted(dated_regs.keys())
        meta = meet_meta.get(meet_key, {})
        venue = normalize_venue(meta.get("venue", ""))
        event_title = meta.get("event_title", "")

        cumulative: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"st_sum": 0.0, "st_count": 0, "name": ""}
        )

        for date_str in dates_sorted:
            output_key = f"{venue}|{date_str}"

            if output_key not in merged_outputs:
                merged_outputs[output_key] = {
                    "generated_at": datetime.now(JST).isoformat(),
                    "venue": venue,
                    "event_title": event_title,
                    "date": date_str,
                    "players": {}
                }

            players_out = merged_outputs[output_key]["players"]

            # この日付ファイルには前日までの累積を入れる
            for reg, src in cumulative.items():
                count = int(src["st_count"])
                if count <= 0:
                    continue

                avg_st = round(src["st_sum"] / count, 2)

                prev = players_out.get(reg)
                if (not prev) or (int(prev.get("count", 0)) < count):
                    players_out[reg] = {
                        "name": src["name"],
                        "avg_st": avg_st,
                        "count": count
                    }

            # その日の結果を翌日以降用の累積へ加算
            current_day_regs = dated_regs[date_str]
            for reg, src in current_day_regs.items():
                cumulative[reg]["st_sum"] += float(src["st_sum"])
                cumulative[reg]["st_count"] += int(src["st_count"])
                if src["name"]:
                    cumulative[reg]["name"] = src["name"]

    out_dir = os.path.join("data", "meet_avg_st")
    clear_output_dir(out_dir)

    written_files = 0

    for _, payload in merged_outputs.items():
        venue = normalize_venue(payload["venue"])
        date_str = payload["date"]
        payload["venue"] = venue
        payload["player_count"] = len(payload["players"])

        file_name = f"{safe_filename_part(venue)}_{date_str}.json"
        out_path = os.path.join(out_dir, file_name)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        written_files += 1

    print("files:", file_count)
    print("races:", race_count)
    print("meet_files:", written_files)
    print("unmatched_rows:", unmatched_rows)
    print("skipped_k0_rows:", skipped_k0_rows)
    print("skipped_f_rows:", skipped_f_rows)
    print("skipped_l_rows:", skipped_l_rows)
    print("out_dir:", out_dir)


if __name__ == "__main__":
    main()