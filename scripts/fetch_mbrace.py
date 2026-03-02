import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))

TODAY_URL = "https://www.boatrace.jp/owpc/pc/race/index"
RACEINDEX_URL = "https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={jcd}&hd={hd}"

ALL_VENUES = [
    ("桐生", "01"), ("戸田", "02"), ("江戸川", "03"), ("平和島", "04"), ("多摩川", "05"), ("浜名湖", "06"),
    ("蒲郡", "07"), ("常滑", "08"), ("津", "09"), ("三国", "10"), ("びわこ", "11"), ("住之江", "12"),
    ("尼崎", "13"), ("鳴門", "14"), ("丸亀", "15"), ("児島", "16"), ("宮島", "17"), ("徳山", "18"),
    ("下関", "19"), ("若松", "20"), ("芦屋", "21"), ("福岡", "22"), ("唐津", "23"), ("大村", "24"),
]
JCD_TO_VENUE = {j: n for n, j in ALL_VENUES}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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
    """
    今日のページ(index)に載ってる開催場は、raceindexへのリンクが必ずある。
    そこから jcd を抜くのが一番ブレない。
    """
    soup = BeautifulSoup(html, "html.parser")

    held_jcds: List[str] = []
    for a in soup.select('a[href*="/owpc/pc/race/raceindex?"]'):
        href = a.get("href") or ""
        # 相対URL/絶対URLどっちでもOKにする
        if href.startswith("/"):
            href_full = "https://www.boatrace.jp" + href
        else:
            href_full = href

        try:
            q = parse_qs(urlparse(href_full).query)
            jcd = (q.get("jcd") or [None])[0]
            if jcd and jcd in JCD_TO_VENUE:
                held_jcds.append(jcd)
        except Exception:
            continue

    # 重複除去（順序保持）
    seen = set()
    out: List[str] = []
    for jcd in held_jcds:
        if jcd not in seen:
            seen.add(jcd)
            out.append(JCD_TO_VENUE[jcd])

    return out


def _parse_cutoff_table_from_raceindex(html: str) -> List[Tuple[int, str]]:
    """
    raceindex の「締切予定時刻」テーブルを構造で読む。
    返り値: [(1, "11:14"), (2, "11:41"), ...]
    """
    soup = BeautifulSoup(html, "html.parser")

    # 「締切予定時刻」を含む th を探す
    th_cutoff = None
    for th in soup.find_all("th"):
        if th.get_text(strip=True) == "締切予定時刻":
            th_cutoff = th
            break
    if not th_cutoff:
        return []

    tr_cutoff = th_cutoff.find_parent("tr")
    if not tr_cutoff:
        return []

    # その直前あたりに「レース」(1R,2R...) の行があるはずなので探す
    table = tr_cutoff.find_parent("table")
    if not table:
        return []

    tr_race = None
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if not ths:
            continue
        if ths[0].get_text(strip=True) == "レース":
            tr_race = tr
            break
    if not tr_race:
        return []

    race_cells = [td.get_text(strip=True) for td in tr_race.find_all("td")]
    time_cells = [td.get_text(strip=True) for td in tr_cutoff.find_all("td")]

    pairs: List[Tuple[int, str]] = []
    for rc, tc in zip(race_cells, time_cells):
        # rc: "1R" tc:"11:14"
        if not rc.endswith("R"):
            continue
        try:
            rno = int(rc[:-1])
        except Exception:
            continue
        if 1 <= rno <= 12 and ":" in tc:
            hh, mm = tc.split(":", 1)
            if hh.isdigit() and mm.isdigit():
                hh_i = int(hh)
                mm_i = int(mm)
                if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
                    pairs.append((rno, f"{hh_i:02d}:{mm_i:02d}"))

    return pairs


def _next_race_for_venue(session: requests.Session, jcd: str, day: datetime, now: datetime) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    次の締切(ISO)と表示文字列を返す:
      (next_race_no, next_cutoff_iso, next_display)
    next_display は "1R 8:00" 形式（時はゼロ埋めしない）
    """
    hd = day.strftime("%Y%m%d")
    url = RACEINDEX_URL.format(jcd=jcd, hd=hd)

    r = session.get(url, timeout=25)
    r.encoding = "utf-8"
    html = r.text
    if _is_blocked(html):
        return None, None, None

    pairs = _parse_cutoff_table_from_raceindex(html)
    if not pairs:
        return None, None, None

    for rno, hhmm in pairs:
        hh, mm = map(int, hhmm.split(":"))
        dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=JST)
        if dt > now:
            display = f"{rno}R {hh}:{mm:02d}"  # ← “8:00” 形式（時だけゼロ埋めしない）
            return rno, dt.isoformat(), display

    return None, None, None


def main():
    now = datetime.now(JST)
    day = now  # 今日

    session = _session()

    # 1) todayページから開催場を確定（raceindexリンクのjcdで拾う）
    r = session.get(TODAY_URL, timeout=25)
    r.encoding = "utf-8"
    html = r.text

    blocked = _is_blocked(html)
    held_places: List[str] = [] if blocked else _extract_held_places_from_today(html)

    # 2) 開催場だけ raceindex を見に行って「次の締切」を決める
    venues = []
    for name, jcd in ALL_VENUES:
        held = name in held_places
        next_race = None
        next_cutoff = None
        next_display = None

        if held and not blocked:
            nr, nc, nd = _next_race_for_venue(session, jcd, day, now)
            next_race, next_cutoff, next_display = nr, nc, nd
            time.sleep(0.25)  # アクセス間引き

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
            "raceindex_url_template": RACEINDEX_URL,
        },
    }

    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()