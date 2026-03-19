# scripts/build_course_stats_from_k.py
# extract_k 内の k******.txt を全部読んで
# 選手ごとのコース別成績を集計する
#
# 出力:
#   data/player_course_stats_all.json
#   data/player_course_stats_1y.json
#   data/player_course_stats_3y.json
#
# 集計項目:
# - starts
# - first
# - second
# - third
# - win_rate
# - ren2_rate
# - ren3_rate
# - avg_st
# - kimarite（逃げ / 差 / まくり / まくり差し / 抜き / 恵まれ）
#
# 補正:
# - コース別平均STの外れ値対策として ST は 0.30 を上限にクリップして集計する
#
# 期間:
# - all : 全期間
# - 1y  : 最新日基準で過去365日分
# - 3y  : 最新日基準で過去1095日分

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

JST = timezone(timedelta(hours=9))

RE_KBGN = re.compile(r"^\d{2}KBGN$")
RE_KEND = re.compile(r"^\d{2}KEND$")
RE_RACE_HEADER = re.compile(r"^\s*(\d{1,2})R")
RE_RESULT_ROW = re.compile(
    r"^\s*([0-9]{2}|S[0-9]|F|K0)\s+([1-6])\s+(\d{4})\s+(.+?)\s+\d+\s+\d+\s+.*?\s+([0-9]+\.[0-9]{2})\s+"
)
RE_KFILE = re.compile(r"^k(\d{2})(\d{2})(\d{2})\.txt$", re.IGNORECASE)

VALID_KIMARITE = {
    "逃げ",
    "差し",
    "まくり",
    "まくり差し",
    "抜き",
    "恵まれ",
}


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


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


def normalize_finish(raw: str) -> Optional[int]:
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    return None


def normalize_course(value: int) -> int:
    return int(value)


def extract_kimarite_nearby(block: List[str], header_idx: int) -> str:
    start = max(0, header_idx - 6)
    end = min(len(block), header_idx + 20)

    for i in range(start, end):
        s = norm_space(block[i])
        if s in VALID_KIMARITE:
            return s

        for k in VALID_KIMARITE:
            if k in s:
                return k

    return ""


def parse_block(block: List[str]) -> List[Dict[str, Any]]:
    races: List[Dict[str, Any]] = []
    current_race: Optional[Dict[str, Any]] = None
    in_result_table = False

    for idx, line in enumerate(block):
        race_head = RE_RACE_HEADER.match(line)
        if race_head and "H1800m" in line:
            if current_race:
                races.append(current_race)

            rno = int(race_head.group(1))
            current_race = {
                "rno": rno,
                "kimarite": extract_kimarite_nearby(block, idx),
                "results": []
            }
            in_result_table = False
            continue

        if current_race is None:
            continue

        if "着 艇 登番" in line:
            in_result_table = True
            continue

        if in_result_table:
            m = RE_RESULT_ROW.match(line)
            if m:
                finish_raw = m.group(1)
                boat_no = int(m.group(2))
                reg = m.group(3)
                name = norm_space(m.group(4))
                st_raw = m.group(5)

                finish = normalize_finish(finish_raw)
                st = None
                try:
                    st = float(st_raw)
                except Exception:
                    st = None

                current_race["results"].append({
                    "reg": reg,
                    "name": name,
                    "boat": boat_no,
                    "course": normalize_course(boat_no),
                    "finish": finish,
                    "st": st
                })
                continue

            if (
                line.strip() == ""
                or line.strip().startswith("単勝")
                or "レース不成立" in line
                or "払戻金" in line
            ):
                in_result_table = False

    if current_race:
        races.append(current_race)

    return races


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


def extract_date_from_k_path(path: str) -> Optional[datetime]:
    name = os.path.basename(path)
    m = RE_KFILE.match(name)
    if not m:
        return None

    yy, mm, dd = map(int, m.groups())
    year = 2000 + yy

    try:
        return datetime(year, mm, dd, tzinfo=JST)
    except Exception:
        return None


def make_empty_course_bucket() -> Dict[str, Any]:
    return {
        "starts": 0,
        "first": 0,
        "second": 0,
        "third": 0,
        "ren2": 0,
        "ren3": 0,
        "st_sum": 0.0,
        "st_count": 0,
        "kimarite": {
            "逃げ": 0,
            "差": 0,
            "まくり": 0,
            "まくり差し": 0,
            "抜き": 0,
            "恵まれ": 0,
        }
    }


def make_empty_player(reg: str, name: str) -> Dict[str, Any]:
    return {
        "reg": reg,
        "name": name or "",
        "courses": {str(i): make_empty_course_bucket() for i in range(1, 7)}
    }


def kimarite_key(raw: str) -> Optional[str]:
    s = norm_space(raw)
    if s == "逃げ":
        return "逃げ"
    if s == "差し":
        return "差"
    if s == "まくり":
        return "まくり"
    if s == "まくり差し":
        return "まくり差し"
    if s == "抜き":
        return "抜き"
    if s == "恵まれ":
        return "恵まれ"
    return None


def ensure_player(players: Dict[str, Dict[str, Any]], reg: str, name: str) -> None:
    if reg not in players:
        players[reg] = make_empty_player(reg, name)
    elif not players[reg].get("name") and name:
        players[reg]["name"] = name


def apply_race_to_players(players: Dict[str, Dict[str, Any]], race: Dict[str, Any]) -> None:
    race_kimarite = race.get("kimarite") or ""
    race_results = race.get("results") or []

    winner = None
    for row in race_results:
        if row.get("finish") == 1:
            winner = row
            break

    for row in race_results:
        reg = str(row.get("reg") or "").strip()
        if not reg:
            continue

        ensure_player(players, reg, row.get("name") or "")

        course = row.get("course")
        if course not in (1, 2, 3, 4, 5, 6):
            continue

        bucket = players[reg]["courses"][str(course)]
        finish = row.get("finish")
        st = row.get("st")

        # starts は正常スタートした完走/通常出走ベース
        # S1, F, K0 は finish が None になるので starts から除外
        if isinstance(finish, int):
            bucket["starts"] += 1

            if finish == 1:
                bucket["first"] += 1
            elif finish == 2:
                bucket["second"] += 1
            elif finish == 3:
                bucket["third"] += 1

            if finish <= 2:
                bucket["ren2"] += 1
            if finish <= 3:
                bucket["ren3"] += 1

        if st is not None:
            st = min(float(st), 0.30)
            bucket["st_sum"] += st
            bucket["st_count"] += 1

        # 決まり手は勝ち選手のコースにだけ加算
        if winner and winner.get("reg") == reg and isinstance(finish, int) and finish == 1:
            kk = kimarite_key(race_kimarite)
            if kk:
                bucket["kimarite"][kk] += 1


def finalize_players(players: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out_players: Dict[str, Any] = {}

    for reg, pdata in players.items():
        course_out: Dict[str, Any] = {}

        for c in range(1, 7):
            src = pdata["courses"][str(c)]
            starts = int(src["starts"])
            first = int(src["first"])
            second = int(src["second"])
            third = int(src["third"])

            if starts > 0:
                win_rate = round(first / starts * 100, 1)
                ren2_rate = round(src["ren2"] / starts * 100, 1)
                ren3_rate = round(src["ren3"] / starts * 100, 1)
            else:
                win_rate = 0.0
                ren2_rate = 0.0
                ren3_rate = 0.0

            avg_st = round(src["st_sum"] / src["st_count"], 2) if src["st_count"] > 0 else None

            course_out[str(c)] = {
                "starts": starts,
                "first": first,
                "second": second,
                "third": third,
                "win_rate": win_rate,
                "ren2_rate": ren2_rate,
                "ren3_rate": ren3_rate,
                "avg_st": avg_st,
                "kimarite": {
                    "逃げ": int(src["kimarite"]["逃げ"]),
                    "差": int(src["kimarite"]["差"]),
                    "まくり": int(src["kimarite"]["まくり"]),
                    "まくり差し": int(src["kimarite"]["まくり差し"]),
                    "抜き": int(src["kimarite"]["抜き"]),
                    "恵まれ": int(src["kimarite"]["恵まれ"]),
                }
            }

        out_players[reg] = {
            "name": pdata["name"],
            "courses": course_out
        }

    return out_players


def write_payload(
    out_path: str,
    file_count: int,
    race_count: int,
    out_players: Dict[str, Any],
    latest_date: str
) -> None:
    payload = {
        "generated_at": datetime.now(JST).isoformat(),
        "latest_file_date": latest_date,
        "source_files": file_count,
        "race_count": race_count,
        "player_count": len(out_players),
        "players": out_players
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    paths = list_k_txt_files()
    if not paths:
        raise FileNotFoundError("k結果txtが見つかりません。data/extract_k を確認してください。")

    file_dates: Dict[str, datetime] = {}
    valid_paths: List[str] = []

    for path in paths:
        dt = extract_date_from_k_path(path)
        if dt is None:
            continue
        file_dates[path] = dt
        valid_paths.append(path)

    if not valid_paths:
        raise FileNotFoundError("日付付きの k結果txt が見つかりません。kYYMMDD.txt 形式を確認してください。")

    latest_dt = max(file_dates.values())
    latest_date_str = latest_dt.strftime("%Y-%m-%d")

    cut_1y = latest_dt - timedelta(days=365)
    cut_3y = latest_dt - timedelta(days=365 * 3)

    players_all: Dict[str, Dict[str, Any]] = {}
    players_1y: Dict[str, Dict[str, Any]] = {}
    players_3y: Dict[str, Dict[str, Any]] = {}

    race_count_all = 0
    race_count_1y = 0
    race_count_3y = 0

    file_count_all = 0
    file_count_1y = 0
    file_count_3y = 0

    for path in sorted(valid_paths):
        file_dt = file_dates[path]
        lines = read_text_auto(path)
        blocks = split_blocks(lines)

        file_count_all += 1
        in_1y = file_dt >= cut_1y
        in_3y = file_dt >= cut_3y

        if in_1y:
            file_count_1y += 1
        if in_3y:
            file_count_3y += 1

        for block in blocks:
            races = parse_block(block)
            if not races:
                continue

            for race in races:
                race_count_all += 1
                apply_race_to_players(players_all, race)

                if in_1y:
                    race_count_1y += 1
                    apply_race_to_players(players_1y, race)

                if in_3y:
                    race_count_3y += 1
                    apply_race_to_players(players_3y, race)

    out_all = finalize_players(players_all)
    out_1y = finalize_players(players_1y)
    out_3y = finalize_players(players_3y)

    os.makedirs("data", exist_ok=True)

    write_payload(
        os.path.join("data", "player_course_stats_all.json"),
        file_count_all,
        race_count_all,
        out_all,
        latest_date_str
    )
    write_payload(
        os.path.join("data", "player_course_stats_1y.json"),
        file_count_1y,
        race_count_1y,
        out_1y,
        latest_date_str
    )
    write_payload(
        os.path.join("data", "player_course_stats_3y.json"),
        file_count_3y,
        race_count_3y,
        out_3y,
        latest_date_str
    )

    print("latest_file_date:", latest_date_str)
    print("all_files:", file_count_all)
    print("all_races:", race_count_all)
    print("all_players:", len(out_all))
    print("out:", os.path.join("data", "player_course_stats_all.json"))

    print("1y_files:", file_count_1y)
    print("1y_races:", race_count_1y)
    print("1y_players:", len(out_1y))
    print("out:", os.path.join("data", "player_course_stats_1y.json"))

    print("3y_files:", file_count_3y)
    print("3y_races:", race_count_3y)
    print("3y_players:", len(out_3y))
    print("out:", os.path.join("data", "player_course_stats_3y.json"))


if __name__ == "__main__":
    main()