import os
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests

JST = timezone(timedelta(hours=9))

VENUES = [
  {"jcd":"01","name":"桐生"}, {"jcd":"02","name":"戸田"}, {"jcd":"03","name":"江戸川"}, {"jcd":"04","name":"平和島"},
  {"jcd":"05","name":"多摩川"}, {"jcd":"06","name":"浜名湖"}, {"jcd":"07","name":"蒲郡"}, {"jcd":"08","name":"常滑"},
  {"jcd":"09","name":"津"}, {"jcd":"10","name":"三国"}, {"jcd":"11","name":"びわこ"}, {"jcd":"12","name":"住之江"},
  {"jcd":"13","name":"尼崎"}, {"jcd":"14","name":"鳴門"}, {"jcd":"15","name":"丸亀"}, {"jcd":"16","name":"児島"},
  {"jcd":"17","name":"宮島"}, {"jcd":"18","name":"徳山"}, {"jcd":"19","name":"下関"}, {"jcd":"20","name":"若松"},
  {"jcd":"21","name":"芦屋"}, {"jcd":"22","name":"福岡"}, {"jcd":"23","name":"唐津"}, {"jcd":"24","name":"大村"},
]

INDEX_URL = "https://www1.mbrace.or.jp/od2/B/dindex.html"

UA = "Mozilla/5.0 (compatible; race-data-bot/1.0; +https://github.com/)"

def now():
    return datetime.now(JST)

def decode_html(res: requests.Response) -> str:
    # mbrace は Shift_JIS 系が多いので安全にデコード
    raw = res.content
    for enc in ("shift_jis", "cp932", "euc_jp", "utf-8"):
        try:
            return raw.decode(enc, errors="ignore")
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")

def fetch(session: requests.Session, url: str):
    res = session.get(url, timeout=30, headers={"User-Agent": UA})
    html = decode_html(res)
    return res, html

def main():
    os.makedirs("data", exist_ok=True)

    with requests.Session() as s:
        # 1) frameset を取得
        r0, index_html = fetch(s, INDEX_URL)

        # 2) dmenu.html を探して取得（ここに会場一覧がいる）
        m = re.search(r'FRAME\s+SRC="([^"]*dmenu\.html[^"]*)"', index_html, flags=re.I)
        menu_url = urljoin(INDEX_URL, m.group(1)) if m else urljoin(INDEX_URL, "dmenu.html")

        r1, menu_html = fetch(s, menu_url)

        # デバッグ用に両方保存（後で確認できる）
        with open("data/source.html", "w", encoding="utf-8") as f:
            f.write(index_html)
        with open("data/source_menu.html", "w", encoding="utf-8") as f:
            f.write(menu_html)

        venues = []
        for v in VENUES:
            # 判定は menu_html を使う（frameset には会場名がない）
            held = v["name"] in menu_html
            venues.append({
                "jcd": v["jcd"],
                "name": v["name"],
                "held": held,
                "status_code": r1.status_code,
                "bytes": len(menu_html),
                "src": "dmenu"
            })

    t = now()

    with open("data/today.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": t.strftime("%Y-%m-%d"),
            "updated_at": t.strftime("%H:%M"),
            "venues": venues
        }, f, ensure_ascii=False, indent=2)

    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump({
            "time": t.strftime("%Y-%m-%d %H:%M"),
            "venues": venues
        }, f, ensure_ascii=False, indent=2)

    with open("data/picks_today.json", "w", encoding="utf-8") as f:
        json.dump({"time": t.strftime("%Y-%m-%d %H:%M"), "picks": []}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()