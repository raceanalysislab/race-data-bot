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

    menu_url = urljoin(BASE, "dmenu.html")

    print("open menu:", menu_url)

    menu_html = fetch(menu_url)

    # メニュー内のリンク全部取る
    pages = re.findall(r'href=["\']([^"\']+\.html)["\']', menu_html, re.I)

    print("===== MENU PAGES =====")

    for p in pages:
        print(p)

    print("===== END =====")

    # 各ページを開いてTXTリンク探す
    for p in pages:

        page_url = urljoin(BASE, p)

        print("open page:", page_url)

        page_html = fetch(page_url)

        txt_links = re.findall(r'href=["\']([^"\']+\.txt)["\']', page_html, re.I)

        for t in txt_links:
            print("TXT:", t)


if __name__ == "__main__":
    main()