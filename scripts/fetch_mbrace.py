import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple

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
VENUE_NAME_TO_JCD = {n: j for n, j in ALL_VENUES}
VENUE_NAMES = [n for n, _ in ALL_VENUES]

TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def _session() -> requests.Session:
    s = requests.Session()

    # 重要：bot判定回避のため最低限ブラウザっぽくする
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
    # 画像の「不正なURLへのリクエストです。」を検出
    return ("不正なURLへのリクエストです" in html) or ("ログインページ" in html and "不正" in html)


def _extract_held_places_from_today(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")

    # 「本日のレース」の表から “行の先頭（場名）” を拾う（ここが一番確実）
    held = []
    for tr in soup.select("table tr"):
        txt = tr.get_text(" ", strip=True)
        # 行テキストに場名が含まれてる行だけ拾う（フッター等の誤検出を避ける）
        for name in VENUE_NAMES:
            if name in txt:
                # 「本日のレース」表っぽい行だけ：締切/開催期間っぽい情報が同じ行にあることが多い
                if ("R" in txt) or ("締切" in txt) or ("発売開始" in txt) or ("日目" in txt) or ("最終日" in txt):
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


def _parse_times_from_raceindex(html: str) -> List[Tuple[int, str]]:
    """
    raceindex のHTMLから (レース番号, "HH:MM") をできるだけ汎用に抜く
    """
    soup = BeautifulSoup(html, "html.parser")

    pairs: List[Tuple[int, str]] = []

    # 行ごとに “nR” と “HH:MM” を探す
    for tr in soup.select("tr"):
        t = tr.get_text(" ", strip=True)
        m_r = re.search(r"\b(\d{1,2})R\b", t)
        m_t = TIME_RE.search(t)
        if not m_r or not m_t:
            continue
        rno = int(m_r.group(1))
        hh = int(m_t.group(1))
        mm = int(m_t.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 1 <= rno <= 12:
            pairs.append((rno, f"{hh:02d}:{mm:02d}"))

    # 重複が出ることあるので、レース番号ごとに最初の1個にする
    dedup: Dict[int, str] = {}
    for rno, tm in pairs:
        dedup.setdefault(rno, tm)

    return sorted(dedup.items(), key=lambda x: x[0])


def _next_race_for_venue(session: requests.Session, jcd: str, day: datetime, now: datetime) -> Tuple[Optional[int], Optional[str]]:
    """
    次の締切(推定)を返す: (next_race_no, next_cutoff_iso)
    """
    hd = day.strftime("%Y%m%d")
    url = RACEINDEX_URL.format(jcd=jcd, hd=hd)

    r = session.get(url, timeout=25)
    r.encoding = "utf-8"
    html = r.text

    # ここでブロックされる場合もある
    if _is_blocked(html):
        return None, None

    pairs = _parse_times_from_raceindex(html)
    if not pairs:
        return None, None

    # ページ内の時刻は基本 “締切予定” の並び（違う場合でも近い指標として使える）
    for rno, hhmm in pairs:
        hh, mm = map(int, hhmm.split(":"))
        dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=JST)
        if dt > now:
            return rno, dt.isoformat()

    return None, None


def main():
    now = datetime.now(JST)
    day = now  # 今日扱い

    session = _session()

    # 1) 今日の開催場を取る
    r = session.get(TODAY_URL, timeout=25)
    r.encoding = "utf-8"
    html = r.text

    held_places: List[str] = []
    blocked = False

    if _is_blocked(html):
        blocked = True
    else:
        held_places = _extract_held_places_from_today(html)

    # 2) 場別に次の締切を取る（開催場だけ）
    venues = []
    for name, jcd in ALL_VENUES:
        held = name in held_places
        next_race = None
        next_cutoff = None
        if held and not blocked:
            nr, nc = _next_race_for_venue(session, jcd, day, now)
            next_race, next_cutoff = nr, nc
            # 連続アクセスしすぎない（相手に優しく）
            time.sleep(0.3)

        venues.append({
            "name": name,
            "jcd": jcd,
            "held": held,
            "next_race": next_race,
            "next_cutoff": next_cutoff,
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

    # 出力
    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()