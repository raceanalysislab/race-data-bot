import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

URL = "https://www.boatrace.jp/owpc/pc/race/index"

ALL_VENUES = [
 "桐生","戸田","江戸川","平和島","多摩川","浜名湖","蒲郡","常滑",
 "津","三国","びわこ","住之江","尼崎","鳴門","丸亀","児島",
 "宮島","徳山","下関","若松","芦屋","福岡","唐津","大村"
]

def main():
    now = datetime.now(JST)

    res = requests.get(URL, timeout=10)
    res.encoding = "utf-8"

    soup = BeautifulSoup(res.text, "html.parser")

    # 開催してる場だけこのclassに出る
    held_nodes = soup.select(".is-place")

    held_today = [n.text.strip() for n in held_nodes]

    venues = []
    for v in ALL_VENUES:
        venues.append({
            "name": v,
            "held": v in held_today
        })

    with open("data/venues_today.json","w",encoding="utf-8") as f:
        json.dump({
            "date": now.strftime("%Y-%m-%d"),
            "held_places": held_today,
            "venues": venues
        }, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()