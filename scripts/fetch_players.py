import re
import requests
from urllib.parse import urljoin

INDEX_URL = "https://www1.mbrace.or.jp/od2/K/dindex.html"


def fetch_text(url: str) -> str:
    r = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
        },
    )
    r.raise_for_status()
    return r.text


def extract_links(html: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    return [urljoin(INDEX_URL, h) for h in hrefs]


def main() -> None:
    print(f"downloading index: {INDEX_URL}")
    html = fetch_text(INDEX_URL)

    links = extract_links(html)

    print("===== ALL LINKS START =====")
    for link in links:
        print(f"LINK: {link}")
    print("===== ALL LINKS END =====")

    if not links:
      raise RuntimeError("リンクが1件も取れませんでした。")


if __name__ == "__main__":
    main()