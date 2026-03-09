import requests
from datetime import datetime

BASE = "https://www1.mbrace.or.jp"
MONTH_DIR = "/od2/K/"

def fetch(url, referer=None):

    headers = {
        "User-Agent": "Mozilla/5.0",
    }

    if referer:
        headers["Referer"] = referer

    r = requests.get(
        url,
        headers=headers,
        timeout=30,
    )

    r.raise_for_status()

    return r.text


def main():

    month = datetime.now().strftime("%Y%m")

    url = f"{BASE}{MONTH_DIR}{month}/"

    print("open month page:", url)

    html = fetch(
        url,
        referer=f"{BASE}{MONTH_DIR}dmenu.html"
    )

    print("===== MONTH PAGE START =====")
    print(html[:5000])
    print("===== MONTH PAGE END =====")


if __name__ == "__main__":
    main()