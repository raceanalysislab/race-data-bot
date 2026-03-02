import json
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
TODAY_URL = "https://www.boatrace.jp/owpc/pc/race/index"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

def now():
    return datetime.now(JST)

def fetch_html():
    r = requests.get(TODAY_URL, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.text

def parse_races(html):
    soup = BeautifulSoup(html, "html.parser")

    venues = []

    blocks = soup.select(".is-tableFixed__3rdadd")

    for block in blocks:
        name_tag = block.select_one(".is-tableFixed__title")
        if not name_tag:
            continue

        venue_name = name_tag.text.strip()

        grade_tag = block.select_one(".is-tableFixed__grade")
        grade = grade_tag.text.strip() if grade_tag else "一般"

        times = block.select(".is-tableFixed__time")

        race_times = []
        for i, t in enumerate(times, start=1):
            txt = t.text.strip()
            if ":" in txt:
                race_times.append((i, txt))

        venues.append({
            "name": venue_name,
            "grade": grade,
            "race_times": race_times
        })

    return venues

def pick_next_race(race_times):
    now_time = now().time()

    for r, t in race_times:
        hh, mm = map(int, t.split(":"))
        deadline = now().replace(hour=hh, minute=mm, second=0).time()

        if now_time < deadline:
            return {
                "next_race": f"{r}R",
                "deadline": t,
                "status": "発売中"
            }

    return {"status": "本日終了"}

def build_output(venues):
    result = []

    for v in venues:
        info = pick_next_race(v["race_times"])

        result.append({
            "name": v["name"],
            "grade": v["grade"],
            **info
        })

    return result

def main():
    html = fetch_html()
    venues = parse_races(html)
    output = build_output(venues)

    with open("data/today.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": now().strftime("%Y-%m-%d"),
            "venues": output
        }, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()