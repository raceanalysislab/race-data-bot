import requests
from urllib.parse import urljoin

BASE = "https://www1.mbrace.or.jp/od2/K/"
INDEX_URL = urljoin(BASE, "dindex.html")
MENU_URL = urljoin(BASE, "dmenu.html")


def fetch(url):
    r = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": BASE,
        },
    )
    r.raise_for_status()
    return r.text


def main():
    print("open index")
    _ = fetch(INDEX_URL)

    print("open menu:", MENU_URL)
    menu_html = fetch(MENU_URL)

    print("===== DMENU HTML FULL START =====")
    print(menu_html)
    print("===== DMENU HTML FULL END =====")


if __name__ == "__main__":
    main()