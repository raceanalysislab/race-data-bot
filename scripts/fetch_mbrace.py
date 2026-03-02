import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))

TODAY_URL = "https://www.boatrace.jp/owpc/pc/race/index"
RACELIST_URL = "https://www.boatrace.jp/owpc/pc/race/racelist?rno=1&jcd={jcd}&hd={hd}"

ALL_VENUES = [
    ("桐生", "01"), ("戸田", "02"), ("江戸川", "03"), ("平和島", "04"), ("多摩川", "05"), ("浜名湖", "06"),
    ("蒲郡", "07"), ("常滑", "08"), ("津", "09"), ("三国", "10"), ("びわこ", "11"), ("住之江", "12"),
    ("尼崎", "13"), ("鳴門", "14"), ("丸亀", "15"), ("児島", "16"), ("宮島", "17"), ("徳山", "18"),
    ("下関", "19"), ("若松", "20"), ("芦屋", "21"), ("福岡", "22"), ("唐津", "23"), ("大村", "24"),
]
VENUE_NAMES = [n for n, _ in ALL_VENUES]

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.boatrace.jp/",
        "Connection": "keep-alive",
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
    s.mount("http://", adapter)
    return s


def _is_blocked(html: str) -> bool:
    return ("不正なURLへのリクエストです" in html) or ("ログインページ" in html and "不正" in html)


def _extract_held_places_from_today(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")

    held = []
    for tr in soup.select("table tr"):
        txt = tr.get_text(" ", strip=True)
        for name in VENUE_NAMES:
            if name in txt:
                # 「本日のレース」表の行っぽい条件
                if ("R" in txt) or ("発売開始" in txt) or ("日目" in txt) or ("最終日" in txt):
                    held.append(name)
                break

    # 重複除去（順序保持）
    seen = set()
    out = []
    for x in held:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _parse_cutoff_row_from_racelist(html: str) -> List[Tuple[int, str]]:
    """
    racelist の「締切予定時刻」行から、(rno, "H:MM") を 1〜12 で返す
    """
    soup = BeautifulSoup(html, "html.parser")

    # まずは “締切予定時刻” を含む行を探す（テーブル構造が変わっても耐える）
    cutoff_tr = None
    for tr in soup.select("tr"):
        if "締切予定時刻" in tr.get_text(" ", strip=True):
            cutoff_tr = tr
            break

    if cutoff_tr is None:
        return []

    # 行の中にある時刻を左から全部拾う（通常12個）
    times = TIME_RE.findall(cutoff_tr.get_text(" ", strip=True))
    if not times:
        return []

    # 12R分を想定して、左から rno=1.. を割り当てる
    pairs: List[Tuple[int, str]] = []
    rno = 1
    for hh, mm in times:
        if rno > 12:
            break
        hh_i = int(hh)
        mm_i = int(mm)
        if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
            # 表示用は先頭ゼロなし（8:00）
            pairs.append((rno, f"{hh_i}:{mm_i:02d}"))
            rno += 1

    return pairs


def _next_race_from_cutoffs(cutoffs: List[Tuple[int, str]], day: datetime, now: datetime) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    (next_race_no, next_cutoff_iso, next_display)
    """
    for rno, hhmm in cutoffs:
        hh, mm = hhmm.split(":")
        dt = datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=JST)
        if dt > now:
            display = f"{rno}R {int(hh)}:{int(mm):02d}"
            return rno, dt.isoformat(), display
    return None, None, None


def main():
    now = datetime.now(JST)
    day = now
    hd = day.strftime("%Y%m%d")

    session = _session()

    # 1) 今日の開催場
    r = session.get(TODAY_URL, timeout=25)
    r.encoding = "utf-8"
    html_today = r.text

    blocked = _is_blocked(html_today)
    held_places: List[str] = [] if blocked else _extract_held_places_from_today(html_today)

    # 2) 開催場だけ racelist を叩いて締切を取る
    venues = []
    for name, jcd in ALL_VENUES:
        held = name in held_places
        next_race = None
        next_cutoff = None
        next_display = None

        if held and not blocked:
            url = RACELIST_URL.format(jcd=jcd, hd=hd)
            rr = session.get(url, timeout=25)
            rr.encoding = "utf-8"
            html_race = rr.text

            if not _is_blocked(html_race):
                cutoffs = _parse_cutoff_row_from_racelist(html_race)
                nr, nc, nd = _next_race_from_cutoffs(cutoffs, day, now)
                next_race, next_cutoff, next_display = nr, nc, nd

            # アクセス間隔（開催場数ぶんだけ）
            time.sleep(0.25)

        venues.append({
            "name": name,
            "jcd": jcd,
            "held": held,
            "next_race": next_race,
            "next_cutoff": next_cutoff,
            "next_display": next_display,
        })

    payload = {
        "date": now.strftime("%Y-%m-%d"),
        "checked_at": now.isoformat(),
        "blocked": blocked,
        "held_places": held_places,
        "venues": venues,
        "source": {
            "today_url": TODAY_URL,
            "racelist_url_template": RACELIST_URL,
        },
    }

    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()