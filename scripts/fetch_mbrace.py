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
    pairs = []

    for idx, (hh, mm) in enumerate(times[:12], start=1):
        pairs.append((idx, f"{int(hh)}:{int(mm):02d}"))

    return pairs


def _next_race(cutoffs, day, now):
    for rno, hhmm in cutoffs:
        hh, mm = map(int, hhmm.split(":"))
        dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=JST)
        if dt > now:
            return rno, dt.isoformat(), f"{rno}R {hh}:{mm:02d}"
    return None, None, None


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
    # 通常は5場以上あることが多い。2場以下なら怪しい。
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

    # --- 3) 開催場だけ締切取得 ---
    venues = []

    for name, jcd in ALL_VENUES:
        held = name in held_today

        next_race = None
        next_cutoff = None
        next_display = None
        cutoffs_out = None

        if held:
            url = RACELIST_URL.format(jcd=jcd, hd=hd)
            rr = session.get(url, timeout=20)
            html = rr.text

            cutoffs = _parse_cutoffs(html)

            if cutoffs:
                cutoffs_out = [{"rno": r, "time": t} for r, t in cutoffs]
                nr, nc, nd = _next_race(cutoffs, now, now)
                next_race, next_cutoff, next_display = nr, nc, nd

            time.sleep(0.35)

        venues.append({
            "name": name,
            "jcd": jcd,
            "held": held,
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