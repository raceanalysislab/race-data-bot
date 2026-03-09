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


def extract_links(html):
    return re.findall(r'href=["\']([^"\']+)["\']', html, re.I)


def main():
    print("open index")
    html = fetch(INDEX_URL)

    menu_match = re.search(r'SRC="([^"]+dmenu\.html)"', html, re.I)

    if not menu_match:
        raise RuntimeError("dmenu.html 見つからない")

    menu_url = urljoin(BASE, menu_match.group(1))

    print("open menu:", menu_url)

    menu_html = fetch(menu_url)

    links = extract_links(menu_html)

    print("===== LINKS =====")

    for l in links:
        print(l)

    print("===== END =====")


if __name__ == "__main__":
    main()