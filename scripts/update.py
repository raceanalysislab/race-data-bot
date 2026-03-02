# scripts/update_today.py
# 完全置き換え用（gradeはgradeschから同期する版 / gradeschの画像(alt/src)対応 / blocked対応）

import json
import os
import re
from datetime import datetime, timezone, timedelta, date

import requests
from bs4 import BeautifulSoup


JST = timezone(timedelta(hours=9))

# 24場
JCD_LIST = [f"{i:02d}" for i in range(1, 25)]

BASE_RACELIST_URL = "https://www.boatrace.jp/owpc/pc/race/racelist"
BASE_GRADESCH_URL = "https://www.boatrace.jp/owpc/pc/race/gradesch"

UA = "Mozilla/5.0 (compatible; race-core-bot/1.0; +https://github.com/)"
OUT_PATH = os.path.join("data", "venues_today.json")

JCD_TO_NAME = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}

# 全角数字→半角数字
_ZEN2HAN = str.maketrans("０１２３４５６７８９", "0123456789")


def jst_now_str() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def hd_today() -> str:
    return datetime.now(JST).strftime("%Y%m%d")


def hd_to_date(hd: str) -> date:
    return date(int(hd[0:4]), int(hd[4:6]), int(hd[6:8]))


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.translate(_ZEN2HAN)
    s = re.sub(r"\s+", "", s)
    return s


def pick_day_by_hd(soup: BeautifulSoup, hd: str) -> str:
    """hd(YYYYMMDD)に一致する『◯月◯日 ◯日目』から日目を拾う"""
    try:
        m = int(hd[4:6])
        d = int(hd[6:8])
    except Exception:
        return ""

    lines = [l.strip() for l in soup.get_text("\n", strip=True).splitlines() if l.strip()]
    md_pat = re.compile(rf"{m}月{d}日")
    for l in lines:
        l2 = normalize_text(l)
        if md_pat.search(l2):
            mm = re.search(r"(\d{1,2})日目", l2)
            if mm:
                return f"{int(mm.group(1))}日目"

    all_text = normalize_text(soup.get_text(" ", strip=True))
    mm = re.search(r"(\d{1,2})日目", all_text)
    return f"{int(mm.group(1))}日目" if mm else ""


def pick_now_race_and_time(soup: BeautifulSoup) -> tuple[str, str]:
    """今のレース番号と締切時刻（簡易）"""
    all_text = soup.get_text("\n", strip=True)

    race = ""
    for key in ["現在", "発売中", "締切"]:
        idx = all_text.find(key)
        if idx != -1:
            window = all_text[max(0, idx - 250): idx + 250]
            m = re.search(r"(\d{1,2})R", window)
            if m:
                race = f"{int(m.group(1))}R"
                break
    if not race:
        m = re.search(r"(\d{1,2})R", all_text)
        if m:
            race = f"{int(m.group(1))}R"

    t = ""
    idx = all_text.find("締切")
    if idx != -1:
        window = all_text[max(0, idx - 250): idx + 250]
        m = re.search(r"(\d{1,2}):(\d{2})", window)
        if m:
            t = f"{int(m.group(1)):02d}:{m.group(2)}"
    if not t:
        m = re.search(r"(\d{1,2}):(\d{2})", all_text)
        if m:
            t = f"{int(m.group(1)):02d}:{m.group(2)}"

    return race, t


def parse_mmdd_range_to_dates(mmdd_range: str, year: int) -> tuple[date, date] | None:
    """'01/29-02/03' -> (YYYY-01-29, YYYY-02-03) / 年跨ぎもケア"""
    s = normalize_text(mmdd_range)
    m = re.match(r"(\d{1,2})/(\d{1,2})-(\d{1,2})/(\d{1,2})", s)
    if not m:
        return None

    sm, sd, em, ed = map(int, m.groups())
    start = date(year, sm, sd)

    end_year = year
    if sm == 12 and em == 1:
        end_year = year + 1
    end = date(end_year, em, ed)
    return start, end


def detect_grade_from_row(tr) -> str | None:
    """
    gradeschの1行(tr)から、画像 alt/src を見てグレードを推定。
    返り値: 'SG'/'PG1'/'G1'/'G2'/'G3' or None
    """
    imgs = tr.find_all("img")
    # alt優先
    for img in imgs:
        alt = (img.get("alt") or "").strip().upper()
        if alt in ("SG", "PG1", "G1", "G2", "G3"):
            return alt

    # src/ファイル名から推定
    for img in imgs:
        src = (img.get("src") or "").lower()
        if "pg1" in src:
            return "PG1"
        if "sg" in src:
            return "SG"
        if "g1" in src:
            return "G1"
        if "g2" in src:
            return "G2"
        if "g3" in src:
            return "G3"

    return None


def detect_venue_name_from_row(tr, known_names: list[str]) -> str | None:
    """
    gradeschの1行(tr)から場名を推定（画像alt or テキスト）。
    """
    imgs = tr.find_all("img")
    for img in imgs:
        alt = (img.get("alt") or "").strip()
        if alt in known_names:
            return alt

    text = tr.get_text(" ", strip=True)
    for name in known_names:
        if name in text:
            return name

    return None


def build_grade_map(hd: str) -> dict[str, str]:
    """
    gradesch(year/hcd=01/02/03) から今日の会場グレードを同期して返す
    戻り: { "14": "G1", "19": "G3", ... }
    """
    target = hd_to_date(hd)
    year = target.year

    name_to_jcd = {v: k for k, v in JCD_TO_NAME.items()}
    known_names = list(name_to_jcd.keys())

    # 初期値: 全部 一般
    grade_map: dict[str, str] = {jcd: "一般" for jcd in JCD_LIST}

    headers = {"User-Agent": UA}
    # SG/PG1, G1/G2, G3 を全部見に行く
    for hcd in ("01", "02", "03"):
        url = f"{BASE_GRADESCH_URL}?hcd={hcd}&year={year}"
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        for tr in soup.find_all("tr"):
            row_text = tr.get_text(" ", strip=True)
            row_norm = normalize_text(row_text)

            mmdd = re.search(r"(\d{1,2}/\d{1,2}-\d{1,2}/\d{1,2})", row_norm)
            if not mmdd:
                continue

            rng = parse_mmdd_range_to_dates(mmdd.group(1), year)
            if not rng:
                continue
            start, end = rng
            if not (start <= target <= end):
                continue

            venue_name = detect_venue_name_from_row(tr, known_names)
            if not venue_name:
                continue
            jcd = name_to_jcd.get(venue_name)
            if not jcd:
                continue

            g = detect_grade_from_row(tr)

            # ページごとの最低保証（画像が拾えないケースの保険）
            if not g:
                if hcd == "01":
                    g = "SG"   # SG/PG1ページ内なので最低SG扱い
                elif hcd == "02":
                    g = "G1"   # G1/G2ページ内なので最低G1扱い
                elif hcd == "03":
                    g = "G3"

            # 優先順位（強いグレードで上書き）
            priority = {"一般": 0, "G3": 1, "G2": 2, "G1": 3, "SG": 4, "PG1": 5}
            if priority.get(g, 0) >= priority.get(grade_map.get(jcd, "一般"), 0):
                grade_map[jcd] = g

    return grade_map


def is_blocked_page(html: str) -> bool:
    """
    boatrace側がブロック/不正URL/ログイン誘導などを返す時を検出
    """
    s = html or ""
    needles = [
        "不正なURLへのリクエストです",
        "ログインページ",
        "アクセスが集中",
        "/login",
    ]
    return any(n in s for n in needles)


def fetch_racelist(jcd: str, hd: str, grade_map: dict[str, str]) -> tuple[bool, dict]:
    url = f"{BASE_RACELIST_URL}?rno=1&jcd={jcd}&hd={hd}"
    headers = {"User-Agent": UA}
    r = requests.get(url, headers=headers, timeout=20)

    html = r.text or ""
    b = len(r.content)

    held = True
    note = "ok"

    # blocked 判定（あなたのJSONに出てたやつ）
    if is_blocked_page(html):
        held = False
        note = "blocked"

    # “no_race” 判定（既存寄せ）
    if held and b <= 20000:
        held = False
        note = "no_race"
    if held and ("該当するデータがありません" in html or "データがありません" in html):
        held = False
        note = "no_race"

    data = {
        "jcd": jcd,
        "name": JCD_TO_NAME.get(jcd, jcd),
        "url": url,
        "status_code": r.status_code,
        "bytes": b,
        "held": held,
        "note": note,
    }

    if not held or r.status_code != 200:
        return held, data

    soup = BeautifulSoup(html, "html.parser")

    # ✅ grade：gradesch同期（開催中のみ表示される前提）
    grade = grade_map.get(jcd, "一般")

    day = pick_day_by_hd(soup, hd)
    race, t = pick_now_race_and_time(soup)

    data.update({
        "grade": grade,
        "day": day,
        "race": race,
        "time": t,
    })

    return held, data


def main():
    hd = hd_today()

    # ✅ 今日のグレード同期を1回だけ作る
    grade_map = build_grade_map(hd)

    venues = []
    errors = []

    for jcd in JCD_LIST:
        try:
            _, item = fetch_racelist(jcd, hd, grade_map)
            venues.append(item)
        except Exception as e:
            errors.append({"jcd": jcd, "error": str(e)})
            venues.append({
                "jcd": jcd,
                "name": JCD_TO_NAME.get(jcd, jcd),
                "url": f"{BASE_RACELIST_URL}?rno=1&jcd={jcd}&hd={hd}",
                "status_code": 0,
                "bytes": 0,
                "held": False,
                "note": "error",
            })

    out = {
        "time": jst_now_str(),
        "hd": hd,
        "count": len(venues),
        "venues": venues,
        "errors": errors,
        "ok": len(errors) == 0,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"wrote: {OUT_PATH}  venues={len(venues)}  errors={len(errors)}")


if __name__ == "__main__":
    main()