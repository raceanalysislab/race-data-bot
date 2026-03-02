import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup

URL = "https://www.boatrace.jp/owpc/pc/race/index"

def main():
    res = requests.get(URL, timeout=10)
    res.encoding = res.apparent_encoding

    soup = BeautifulSoup(res.text, "html.parser")

    venues = []

    cards = soup.select(".table1 tbody tr")

    for row in cards:
        name_tag = row.select_one(".place")
        if not name_tag:
            continue

        name = name_tag.text.strip()

        time_tag = row.select_one(".deadtime")
        deadline = time_tag.text.strip() if time_tag else ""

        venues.append({
            "name": name,
            "deadline": deadline
        })

    data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "venues": venues
    }

    with open("data/today.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()