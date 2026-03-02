import os
import json
from datetime import datetime, timedelta, timezone
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

URL = "https://www1.mbrace.or.jp/od2/B/dindex.html"

def now():
    return datetime.now(JST)

def main():
    os.makedirs("data", exist_ok=True)

    r = requests.get(URL, timeout=30)
    html = r.text

    with open("data/source.html","w",encoding="utf-8") as f:
        f.write(html)

    venues = []
    for v in VENUES:
        held = v["name"] in html
        venues.append({
            "jcd": v["jcd"],
            "name": v["name"],
            "held": held,
            "status_code": r.status_code,
            "bytes": len(html)
        })

    t = now()

    with open("data/today.json","w",encoding="utf-8") as f:
        json.dump({
            "date": t.strftime("%Y-%m-%d"),
            "updated_at": t.strftime("%H:%M"),
            "venues": venues
        },f,ensure_ascii=False,indent=2)

    with open("data/venues_today.json","w",encoding="utf-8") as f:
        json.dump({
            "time": t.strftime("%Y-%m-%d %H:%M"),
            "venues": venues
        },f,ensure_ascii=False,indent=2)

    with open("data/picks_today.json","w",encoding="utf-8") as f:
        json.dump({"time":t.strftime("%Y-%m-%d %H:%M"),"picks":[]},f)

if __name__ == "__main__":
    main()