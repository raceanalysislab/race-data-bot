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

# HH:MM を拾う（例: 8:00 / 08:00）
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
    # 代表的なブロック文言/画面をざっくり検出
    return ("不正なURLへのリクエストです" in html) or ("ログインページ" in html and "不正" in html) or ("アクセスが集中" in html and "お待ち" in html)


def _extract_held_places_from_today(html: str) -> List[str]:
    """
    todayページから開催場名を抽出（あなたの現行方式を維持）
    """
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


def _normalize_hhmm(hh: str, mm: str) -> str:
    # 表示用：先頭ゼロ無し 8:00 形式
    return f"{int(hh)}:{int(mm):02d}"


def _parse_cutoffs_from_racelist(html: str) -> List[Tuple[int, str]]:
    """
    racelist から 1〜12R の締切(推定)を取る。
    1) まず “締切予定時刻” 行を探す（最優先）
    2) 見つからない場合はページ全体から時刻を拾って12個に近い塊を使う（保険）
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1) “締切予定時刻” 行を優先
    cutoff_tr = None
    for tr in soup.select("tr"):
        if "締切予定時刻" in tr.get_text(" ", strip=True):
            cutoff_tr = tr
            break

    times: List[Tuple[str, str]] = []
    if cutoff_tr is not None:
        times = TIME_RE.findall(cutoff_tr.get_text(" ", strip=True))

    # 2) 保険：行が取れない場合は、ページ全体から “時刻” を拾う
    #    （構造変わっても最低限の復旧を狙う）
    if not times:
        all_times = TIME_RE.findall(soup.get_text(" ", strip=True))
        # 全体から拾うと多すぎる場合があるので、12個以上連続で取れるケースに期待する
        # ここは「左から12個」を使う（最悪でも next 判定が動く）
        if len(all_times) >= 12:
            times = all_times[:12]
        else:
            times = all_times

    if not times:
        return []

    pairs: List[Tuple[int, str]] = []
    rno = 1
    for hh, mm in times:
        if rno > 12:
            break
        hh_i = int(hh)
        mm_i = int(mm)
        if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
            pairs.append((rno, _normalize_hhmm(hh, mm)))
            rno += 1

    # 12個未満でも返す（開催形態や表示欠損に備える）
    return pairs


def _next_race_from_cutoffs(
    cutoffs: List[Tuple[int, str]],
    day: datetime,
    now: datetime,
) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    (next_race_no, next_cutoff_iso, next_display)
    """
    for rno, hhmm in cutoffs:
        hh_s, mm_s = hhmm.split(":")
        dt = datetime(day.year, day.month, day.day, int(hh_s), int(mm_s), tzinfo=JST)
        if dt > now:
            display = f"{rno}R {int(hh_s)}:{int(mm_s):02d}"
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
    if blocked:
        print("[WARN] TODAY page looks blocked.")
        held_places: List[str] = []
    else:
        held_places = _extract_held_places_from_today(html_today)

    # 2) 開催場だけ racelist を叩いて締切を取る
    venues = []
    for name, jcd in ALL_VENUES:
        held = (name in held_places) and (not blocked)

        next_race = None
        next_cutoff = None
        next_display = None
        cutoffs_out: Optional[List[Dict[str, object]]] = None

        if held:
            url = RACELIST_URL.format(jcd=jcd, hd=hd)
            rr = session.get(url, timeout=25)
            rr.encoding = "utf-8"
            html_race = rr.text

            if _is_blocked(html_race):
                print(f"[WARN] RACELIST blocked for {name} (jcd={jcd}) url={url}")
            else:
                cutoffs = _parse_cutoffs_from_racelist(html_race)

                if not cutoffs:
                    print(f"[WARN] No cutoffs parsed for {name} (jcd={jcd}) url={url}")
                else:
                    # JSONに12R一覧を残す（運用の保険）
                    cutoffs_out = [{"rno": rno, "time": hhmm} for rno, hhmm in cutoffs]

                    nr, nc, nd = _next_race_from_cutoffs(cutoffs, day, now)
                    next_race, next_cutoff, next_display = nr, nc, nd

                    # 全部終わってる場合でも一覧は残す
                    if next_race is None:
                        print(f"[INFO] All cutoffs passed for {name} (jcd={jcd}).")

            # アクセス間隔（開催場数ぶんだけ / ちょい優しめ）
            time.sleep(0.35)

        venues.append({
            "name": name,
            "jcd": jcd,
            "held": held,
            "next_race": next_race,
            "next_cutoff": next_cutoff,
            "next_display": next_display,
            "cutoffs": cutoffs_out,  # held=false なら null のまま
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