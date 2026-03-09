import os
import subprocess
from datetime import datetime, timedelta, timezone

import requests

JST = timezone(timedelta(hours=9))

BASE = "https://www1.mbrace.or.jp/od2/K/"
DOWNLOAD_DIR = "data/download_k"
EXTRACT_DIR = "data/extract_k"

USER_AGENT = "Mozilla/5.0"


def ensure_dirs():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(EXTRACT_DIR, exist_ok=True)


def yymmdd(dt: datetime) -> str:
    return dt.strftime("%y%m%d")


def build_url(dt: datetime) -> str:
    return f"{BASE}k{yymmdd(dt)}.lzh"


def download_file(url: str, dest_path: str) -> bool:
    r = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )

    if r.status_code != 200:
        print(f"skip: {r.status_code} {url}")
        return False

    with open(dest_path, "wb") as f:
        f.write(r.content)

    return True


def extract_lzh(lzh_path: str):
    subprocess.run(
        ["lhasa", "x", os.path.abspath(lzh_path)],
        cwd=EXTRACT_DIR,
        check=True,
    )


def collect_dates(days: int = 30):
    now = datetime.now(JST)
    return [now - timedelta(days=i) for i in range(days)]


def already_done(dt: datetime) -> bool:
    txt_path = os.path.join(EXTRACT_DIR, f"k{yymmdd(dt)}.txt")
    return os.path.exists(txt_path)


def try_one(dt: datetime):
    yy = yymmdd(dt)
    url = build_url(dt)
    lzh_path = os.path.join(DOWNLOAD_DIR, f"k{yy}.lzh")

    if already_done(dt):
        print(f"exists: k{yy}.txt")
        return True

    print("try:", url)

    ok = download_file(url, lzh_path)
    if not ok:
        return False

    try:
        extract_lzh(lzh_path)
        print(f"success: k{yy}.txt")
        return True
    except Exception as e:
        print(f"extract error: {url} {e}")
        return False


def main():
    ensure_dirs()

    dates = collect_dates(days=30)

    success_count = 0

    for dt in dates:
        if try_one(dt):
            success_count += 1

    print(f"done: success_count={success_count}")


if __name__ == "__main__":
    main()