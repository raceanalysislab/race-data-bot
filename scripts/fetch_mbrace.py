import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))

# ✅ これだけ使う（jcd付き index）
INDEX_JCD_URL = "https://www.boatrace.jp/owpc/pc/race/index?jcd={jcd}"

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
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.boatrace.jp/",
    })

    retry = Retry(
        total=4,
        backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("https://", adapter)
    return s


def _looks_like_mbrace(html: str) -> bool:
    # ✅ boatrace じゃなく mbrace の選択ページに飛ばされてる/拾ってるパターンを弾く
    return "mbrace.or.jp" in html or "Today's Race Information Index" in html or "ダウンロード開始" in html


def _normalize_grade(text: str) -> str:
    if not text:
        return ""

    t = text.strip()

    # 全角→半角っぽく寄せる（最低限）
    t = t.replace("Ｇ", "G").replace("Ⅰ", "I").replace("Ⅱ", "II").replace("Ⅲ", "III")

    # よくある表記ゆれ
    t = t.upper()
    t = t.replace("GⅠ", "G1").replace("GI", "G1")
    t = t.replace("GⅡ", "G2").replace("GII", "G2")
    t = t.replace("GⅢ", "G3").replace("GIII", "G3")

    # SG / G1 / G2 / G3 を拾う
    if "SG" in t:
        return "SG"
    if "G1" in t:
        return "G1"
    if "G2" in t:
        return "G2"
    if "G3" in t:
        return "G3"
    return ""


def _extract_grade_and_day(page_text: str) -> Tuple[str, str]:
    """
    ✅ index?jcd=XX のページ全体テキストから
    - grade: SG/G1/G2/G3/一般(空なら一般扱い)
    - day  : 初日 / 2日目 / ... / 最終日
    を抜く（セレクタ依存を減らす）
    """
    t = re.sub(r"\s+", " ", page_text or "").strip()

    # day
    day = ""
    if "最終日" in t:
        day = "最終日"
    elif "初日" in t:
        day = "初日"
    else:
        m = re.search(r"(\d{1,2})日目", t)
        if m:
            day = f"{m.group(1)}日目"

    # grade
    grade = _normalize_grade(t)

    return grade, day


def _parse_cutoffs_from_index(html: str) -> List[Tuple[int, str]]:
    """
    ✅ index?jcd=XX の中にある「締切予定時刻」行から 1〜12R の HH:MM を抜く
    """
    soup = BeautifulSoup(html, "html.parser")

    cutoff_tr = None
    for tr in soup.select("tr"):
        if "締切予定時刻" in tr.get_text(" ", strip=True):
            cutoff_tr = tr
            break

    if not cutoff_tr:
        # 念のためページ全体から「締切予定時刻」周辺を探す
        full = soup.get_text(" ", strip=True)
        if "締切予定時刻" not in full:
            return []
        # 全体から時刻だけ抜く（最後の砦）
        times = TIME_RE.findall(full)
        pairs = []
        for idx, (hh, mm) in enumerate(times[:12], start=1):
            pairs.append((idx, f"{int(hh)}:{int(mm):02d}"))
        return pairs

    times = TIME_RE.findall(cutoff_tr.get_text(" ", strip=True))
    pairs = []
    for idx, (hh, mm) in enumerate(times[:12], start=1):
        pairs.append((idx, f"{int(hh)}:{int(mm):02d}"))
    return pairs


def _next_race(cutoffs: List[Tuple[int, str]], today: datetime, now: datetime) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    for rno, hhmm in cutoffs:
        hh, mm = map(int, hhmm.split(":"))
        dt = datetime(today.year, today.month, today.day, hh, mm, tzinfo=JST)
        # ✅ 締切時刻になった瞬間に次へ（dt > now のみ）
        if dt > now:
            return rno, dt.isoformat(), f"{rno}R {hh}:{mm:02d}"
    return None, None, "終了"


def _is_not_held(page_text: str) -> bool:
    t = page_text or ""
    # 典型的な「開催なし」系メッセージを拾う（表記ゆれ対策でざっくり）
    keywords = [
        "本日は開催しておりません",
        "本場開催はありません",
        "開催はありません",
        "ただいま開催情報はありません",
    ]
    return any(k in t for k in keywords)


def main():
    now = datetime.now(JST)
    session = _session()

    venues_out: List[Dict] = []
    held_places: List[str] = []
    blocked = False

    for name, jcd in ALL_VENUES:
        url = INDEX_JCD_URL.format(jcd=jcd)

        try:
            r = session.get(url, timeout=20)
            html = r.text
        except Exception as e:
            venues_out.append({
                "name": name,
                "jcd": jcd,
                "held": False,
                "grade": "",
                "day": "",
                "next_race": None,
                "next_cutoff": None,
                "next_display": None,
                "cutoffs": None,
                "note": f"fetch_error:{type(e).__name__}",
            })
            continue

        # ✅ mbrace HTMLを拾ってたら「blocked」扱い（全会場 false に倒すのではなく、単体で弾く）
        if _looks_like_mbrace(html):
            blocked = True
            venues_out.append({
                "name": name,
                "jcd": jcd,
                "held": False,
                "grade": "",
                "day": "",
                "next_race": None,
                "next_cutoff": None,
                "next_display": None,
                "cutoffs": None,
                "note": "blocked_or_wrong_html(mbrace_like)",
            })
            time.sleep(0.2)
            continue

        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(" ", strip=True)

        # ✅ 開催なし
        if _is_not_held(page_text):
            venues_out.append({
                "name": name,
                "jcd": jcd,
                "held": False,
                "grade": "",
                "day": "",
                "next_race": None,
                "next_cutoff": None,
                "next_display": None,
                "cutoffs": None,
                "note": "not_held",
            })
            time.sleep(0.25)
            continue

        cutoffs = _parse_cutoffs_from_index(html)
        # ✅ cutoffsが取れない = 開催判定できないので held:false に倒す（誤爆でSG/初日固定にならないように）
        if not cutoffs:
            venues_out.append({
                "name": name,
                "jcd": jcd,
                "held": False,
                "grade": "",
                "day": "",
                "next_race": None,
                "next_cutoff": None,
                "next_display": None,
                "cutoffs": None,
                "note": "no_cutoffs_found",
            })
            time.sleep(0.25)
            continue

        grade, day = _extract_grade_and_day(page_text)

        nr, nc, nd = _next_race(cutoffs, now, now)

        venues_out.append({
            "name": name,
            "jcd": jcd,
            "held": True,
            "grade": grade,   # "SG"/"G1"/"G2"/"G3"/""(一般)
            "day": day,       # "初日"/"2日目"/"最終日"/""(不明)
            "next_race": nr,
            "next_cutoff": nc,
            "next_display": nd,
            "cutoffs": [{"rno": rno, "time": t} for rno, t in cutoffs],
            "note": "",
        })
        held_places.append(name)

        time.sleep(0.35)

    payload = {
        "date": now.strftime("%Y-%m-%d"),
        "checked_at": now.isoformat(),
        "blocked": blocked,
        "held_places": held_places,
        "venues": venues_out,
    }

    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()