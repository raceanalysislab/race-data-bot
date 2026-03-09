import requests

INDEX_URL = "https://www1.mbrace.or.jp/od2/K/dindex.html"


def main():
    r = requests.get(
        INDEX_URL,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Referer": "https://www1.mbrace.or.jp/",
            "Accept-Language": "ja-JP,ja;q=0.9",
        },
    )
    r.raise_for_status()

    print("status:", r.status_code)
    print("content-type:", r.headers.get("Content-Type"))
    print("final-url:", r.url)
    print("===== HTML HEAD START =====")
    print(r.text[:3000])
    print("===== HTML HEAD END =====")


if __name__ == "__main__":
    main()