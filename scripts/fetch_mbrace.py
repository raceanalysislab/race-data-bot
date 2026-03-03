import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional, Dict

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))

# ✅ 開催場一覧（todayページ）
TODAY_URL = "https://www.boatrace.jp/owpc/pc/race/index"
# ✅ 各場のトップ（grade/day を取る。racelist はブロックされることがある）
INDEX_URL = "https://www.boatrace.jp/owpc/pc/race/index?jcd={jcd}"
# ✅ 締切（cutoffs）取得は racelist
RACELIST_URL = "https://www.boatrace.jp/owpc/pc/race/racelist?rno=1&jcd={jcd}&hd={hd}"

ALL_VENUES = [
    ("桐生", "01"), ("戸田", "02"), ("江戸川", "03"), ("平和島", "04"), ("多摩川", "05"), ("浜名湖", "06"),
    ("蒲郡", "07"), ("常滑", "08"), ("津", "09"), ("三国", "10"), ("びわこ", "11"), ("住之江", "12"),
    ("尼崎", "13"), ("鳴門", "14"), ("丸亀", "15"), ("児島", "16"), ("宮島", "17"), ("徳山", "18"),
    ("下関", "19"), ("若松", "20"), ("芦屋", "21"), ("福岡", "22"), ("唐津", "23"), ("大村", "24"),
]

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.boatrace.jp/",
    })

    retry = Retry(
        total=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    return s


def _is_blocked(html: str) -> bool:
    return "不正なURLへのリクエストです" in html


def _normalize_ascii(s: str) -> str:
    """全角英数→半角、ローマ数字等も寄せて、比較しやすくする"""
    if not s:
        return ""
    s = str(s)
    s = s.replace("Ｇ", "G").replace("Ｓ", "S")
    s = s.replace("Ⅰ", "I").replace("Ⅱ", "II").replace("Ⅲ", "III")
    # 全角→半角
    s = s.translate(str.maketrans({
        "０":"0","１":"1","２":"2","３":"3","４":"4","５":"5","６":"6","７":"7","８":"8","９":"9",
        "Ａ":"A","Ｂ":"B","Ｃ":"C","Ｄ":"D","Ｅ":"E","Ｆ":"F","Ｇ":"G","Ｈ":"H","Ｉ":"I","Ｊ":"J","Ｋ":"K","Ｌ":"L","Ｍ":"M",
        "Ｎ":"N","Ｏ":"O","Ｐ":"P","Ｑ":"Q","Ｒ":"R","Ｓ":"S","Ｔ":"T","Ｕ":"U","Ｖ":"V","Ｗ":"W","Ｘ":"X","Ｙ":"Y","Ｚ":"Z",
        "ａ":"a","ｂ":"b","ｃ":"c","ｄ":"d","ｅ":"e","ｆ":"f","ｇ":"g","ｈ":"h","ｉ":"i","ｊ":"j","ｋ":"k","ｌ":"l","ｍ":"m",
        "ｎ":"n","ｏ":"o","ｐ":"p","ｑ":"q","ｒ":"r","ｓ":"s","ｔ":"t","ｕ":"u","ｖ":"v","ｗ":"w","ｘ":"x","ｙ":"y","ｚ":"z",
    }))
    return s


def _extract_held_from_today(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    held = []
    for name, _ in ALL_VENUES:
        if name in text:
            held.append(name)
    return held


def _parse_cutoffs(html: str) -> List[Tuple[int, str]]:
    soup = BeautifulSoup(html, "html.parser")

    cutoff_tr = None
    for tr in soup.select("tr"):
        if "締切予定時刻" in tr.get_text(" ", strip=True):
            cutoff_tr = tr
            break

    if not cutoff_tr:
        return []

    times = TIME_RE.findall(cutoff_tr.get_text(" ", strip=True))
    pairs: List[Tuple[int, str]] = []
    for idx, (hh, mm) in enumerate(times[:12], start=1):
        pairs.append((idx, f"{int(hh)}:{int(mm):02d}"))
    return pairs


def _next_race(cutoffs: List[Tuple[int, str]], now: datetime) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """cutoffsは (rno, 'H:MM')。now より未来の最初を次とする。"""
    for rno, hhmm in cutoffs:
        hh, mm = map(int, hhmm.split(":"))
        dt = datetime(now.year, now.month, now.day, hh, mm, tzinfo=JST)
        if dt > now:
            return rno, dt.isoformat(), f"{rno}R {hh}:{mm:02d}"
    return None, None, None


def _pick_grade(text: str) -> str:
    """
    indexページから grade を雑にでも安定して拾う。
    返り値は '', '一般', 'SG', 'G1', 'G2', 'G3'
    """
    t = _normalize_ascii(text).upper().replace(" ", "").replace("\u3000", "")
    # よくある表記揺れを寄せる
    t = t.replace("GI", "G1").replace("GII", "G2").replace("GIII", "G3")
    t = t.replace("GⅠ", "G1").replace("GⅡ", "G2").replace("GⅢ", "G3")

    if "SG" in t:
        return "SG"
    if "G1" in t:
        return "G1"
    if "G2" in t:
        return "G2"
    if "G3" in t:
        return "G3"
    if "一般" in text:
        return "一般"
    return ""


def _pick_day_label(soup: BeautifulSoup) -> str:
    """
    indexページの「初日/2日目/…/最終日」を拾う。
    - まず「アクティブっぽい要素」から探す
    - ダメならページ内の出現を拾う
    """
    # 1) classに active/current/selected が入ってる要素から拾う（雑に複数パターン）
    candidates = soup.select(
        ".is-active, .is-current, .is-selected, .active, .current, .selected, "
        ".tab1.is-active, .tab2.is-active, .tab3.is-active, "
        ".tabs .is-active, .tab .is-active"
    )
    day_words = ["初日", "2日目", "3日目", "4日目", "5日目", "6日目", "最終日", "前検日"]

    for el in candidates:
        txt = el.get_text(" ", strip=True)
        for w in day_words:
            if w in txt:
                return w

    # 2) それっぽいタブ領域を広く見る（上部の日程並び）
    # boatraceのindexは上部に日程ラベルが並ぶので、短いテキストから拾う
    for el in soup.find_all(["li", "a", "span", "div"]):
        txt = el.get_text(" ", strip=True)
        if not txt or len(txt) > 8:
            continue
        for w in day_words:
            if txt == w:
                # ここで active 判定ができないので、見つかったら一旦保持候補にする
                return w

    # 3) 最後に本文テキスト全体から拾う（最後の保険）
    full = soup.get_text("\n", strip=True)
    for w in day_words:
        if w in full:
            return w

    return ""


def _parse_grade_and_day_from_index(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    grade = _pick_grade(text)
    day = _pick_day_label(soup)

    return grade, day


def main():
    now = datetime.now(JST)
    hd = now.strftime("%Y%m%d")

    session = _session()

    # --- 1) today取得 ---
    r = session.get(TODAY_URL, timeout=20)
    html_today = r.text

    blocked = _is_blocked(html_today)
    held_today = [] if blocked else _extract_held_from_today(html_today)

    # --- 2) 安定化：todayが少なすぎる場合は補完 ---
    if len(held_today) <= 2:
        print("[INFO] Fallback racelist check triggered.")
        held_today = []

        for name, jcd in ALL_VENUES:
            url = RACELIST_URL.format(jcd=jcd, hd=hd)
            rr = session.get(url, timeout=20)
            html = rr.text

            if not _is_blocked(html):
                cutoffs = _parse_cutoffs(html)
                if cutoffs:
                    held_today.append(name)

            time.sleep(0.2)

    # --- 3) 開催場だけ：grade/day と 締切取得 ---
    venues = []

    for name, jcd in ALL_VENUES:
        held = name in held_today

        next_race = None
        next_cutoff = None
        next_display = None
        cutoffs_out = None

        grade = ""
        day = ""

        if held:
            # ✅ grade/day は index?jcd=xx から取る（ブロック回避）
            idx_url = INDEX_URL.format(jcd=jcd)
            ir = session.get(idx_url, timeout=20)
            idx_html = ir.text
            if not _is_blocked(idx_html):
                g, d = _parse_grade_and_day_from_index(idx_html)
                grade = g
                day = d
            time.sleep(0.15)

            # ✅ cutoffs は racelist
            url = RACELIST_URL.format(jcd=jcd, hd=hd)
            rr = session.get(url, timeout=20)
            html = rr.text

            cutoffs = _parse_cutoffs(html)
            if cutoffs:
                cutoffs_out = [{"rno": rno, "time": t} for rno, t in cutoffs]
                nr, nc, nd = _next_race(cutoffs, now)
                next_race, next_cutoff, next_display = nr, nc, nd

            time.sleep(0.35)

        venues.append({
            "name": name,
            "jcd": jcd,
            "held": held,

            # ✅ 追加
            "grade": grade,   # "一般" / "SG" / "G1" / "G2" / "G3" / ""
            "day": day,       # "初日" / "2日目" / ... / "最終日" / ""

            "next_race": next_race,
            "next_cutoff": next_cutoff,
            "next_display": next_display,
            "cutoffs": cutoffs_out,
        })

    payload = {
        "date": now.strftime("%Y-%m-%d"),
        "checked_at": now.isoformat(),
        "blocked": blocked,
        "held_places": held_today,
        "venues": venues,
    }

    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()