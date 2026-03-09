import requests
from datetime import datetime

BASE = "https://www1.mbrace.or.jp/od2/K/"

def fetch(url):

    r = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
        },
        timeout=30
    )

    r.raise_for_status()

    return r.text


def main():

    today = datetime.now()

    yymmdd = today.strftime("%y%m%d")

    url = f"{BASE}B{yymmdd}.TXT"

    print("fetch:", url)

    data = fetch(url)

    print("===== TXT START =====")
    print(data[:2000])
    print("===== TXT END =====")


if __name__ == "__main__":
    main()