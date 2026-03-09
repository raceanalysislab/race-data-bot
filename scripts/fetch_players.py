import re
import requests
from urllib.parse import urljoin

BASE = "https://www1.mbrace.or.jp/od2/K/"
INDEX_URL = urljoin(BASE, "dindex.html")


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

    html = fetch(INDEX_URL)

    # 大文字小文字無視で dmenu.html を探す
    match = re.search(r'dmenu\.html', html, re.IGNORECASE)

    if not match:
        raise RuntimeError("dmenu.html 見つからない")

    menu_url = urljoin(BASE, "dmenu.html")

    print("open menu:", menu_url)

    menu_html = fetch(menu_url)

    links = re.findall(r'href=["\']([^"\']+)["\']', menu_html, re.I)

    print("===== LINKS =====")

    for l in links:
        print(l)

    print("===== END =====")


if __name__ == "__main__":
    main()