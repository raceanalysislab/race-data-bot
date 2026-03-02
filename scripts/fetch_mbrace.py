import os
import re
import json
from datetime import datetime, timedelta, timezone
import requests
from urllib.parse import urljoin

JST = timezone(timedelta(hours=9))

VENUES = [
  {"jcd":"01","name":"桐生"}, {"jcd":"02","name":"戸田"}, {"jcd":"03","name":"江戸川"}, {"jcd":"04","name":"平和島"},
  {"jcd":"05","name":"多摩川"}, {"jcd":"06","name":"浜名湖"}, {"jcd":"07","name":"蒲郡"}, {"jcd":"08","name":"常滑"},
  {"jcd":"09","name":"津"}, {"jcd":"10","name":"三国"}, {"jcd":"11","name":"びわこ"}, {"jcd":"12","name":"住之江"},
  {"jcd":"13","name":"尼崎"}, {"jcd":"14","name":"鳴門"}, {"jcd":"15","name":"丸亀"}, {"jcd":"16","name":"児島"},
  {"jcd":"17","name":"宮島"}, {"jcd":"18","name":"徳山"}, {"jcd":"19","name":"下関"}, {"jcd":"20","name":"若松"},
  {"jcd":"21","name":"芦屋"}, {"jcd":"22","name":"福岡"}, {"jcd":"23","name":"唐津"}, {"jcd":"24","name":"大村"},
]

BASE_URL = "https://www1.mbrace.or.jp/od2/B/"
START_URL = urljoin(BASE_URL, "dindex.html")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

def now():
    return datetime.now(JST)

def fetch_text(url: str) -> tuple[int, str]:
    r = requests.get(url, timeout=30, headers=HEADERS)
    # 文字化け対策（Shift_JIS系が混ざる）
    r.encoding = r.apparent_encoding
    return r.status_code, r.text

FRAME_RE = re.compile(r'<frame[^>]+src="([^"]+)"', re.IGNORECASE)

def follow_frameset_until_content(start_url: str, max_hops: int = 5) -> tuple[str, int, str]:
    """
    framesetだけのHTMLなら、FRAME SRCを辿って本文っぽいHTMLを探す。
    最後に到達したURL, status_code, html を返す。
    """
    url = start_url
    last_status, html = fetch_text(url)

    for _ in range(max_hops):
        lower = html.lower()
        if "<frameset" not in lower and "<frame" not in lower:
            return url, last_status, html  # 本文っぽい

        # frame src を全部拾う
        srcs = FRAME_RE.findall(html)
        if not srcs:
            return url, last_status, html

        # まず「menu」「dmenu」を含むものを優先、なければ先頭
        cand = None
        for s in srcs:
            s_low = s.lower()
            if "menu" in s_low:
                cand = s
                break
        if cand is None:
            cand = srcs[0]

        url = urljoin(url, cand)
        last_status, html = fetch_text(url)

    return url, last_status, html

def main():
    os.makedirs("data", exist_ok=True)

    # 入口 → frameset辿って本文へ
    final_url, sc, html = follow_frameset_until_content(START_URL, max_hops=6)

    # デバッグ保存（まずはこれ見れば100%分かる）
    with open("data/source_final_url.txt", "w", encoding="utf-8") as f:
        f.write(final_url)

    with open("data/source.html", "w", encoding="utf-8") as f:
        f.write(html)

    venues = []
    for v in VENUES:
        held = v["name"] in html
        venues.append({
            "jcd": v["jcd"],
            "name": v["name"],
            "held": held,
            "status_code": sc,
            "bytes": len(html)
        })

    t = now()

    with open("data/today.json","w",encoding="utf-8") as f:
        json.dump({
            "date": t.strftime("%Y-%m-%d"),
            "updated_at": t.strftime("%H:%M"),
            "venues": venues
        }, f, ensure_ascii=False, indent=2)

    with open("data/venues_today.json","w",encoding="utf-8") as f:
        json.dump({
            "time": t.strftime("%Y-%m-%d %H:%M"),
            "venues": venues
        }, f, ensure_ascii=False, indent=2)

    with open("data/picks_today.json","w",encoding="utf-8") as f:
        json.dump({"time": t.strftime("%Y-%m-%d %H:%M"), "picks": []}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()