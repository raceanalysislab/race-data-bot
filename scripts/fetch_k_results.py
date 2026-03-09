import os
import subprocess
from datetime import datetime, timedelta, timezone

import requests

JST = timezone(timedelta(hours=9))

BASE = "https://www1.mbrace.or.jp/od2/K"
DOWNLOAD_DIR = "data/download_k"
EXTRACT_DIR = "data/extract_k"

USER_AGENT = "Mozilla/5.0"

# まずは3年分
FETCH_DAYS = 365 * 3


def ensure_dirs():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(EXTRACT_DIR, exist_ok=True)


def yymmdd(dt: datetime) -> str:
    return dt.strftime("%y%m%d")


def yyyymm(dt: datetime) -> str:
    return dt.strftime("%Y%m")


def build_url(dt: datetime) -> str:
    return f"{BASE}/{yyyymm(dt)}/k{yymmdd(dt)}.lzh"


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


def collect_dates(days: int = FETCH_DAYS):
    now = datetime.now(JST)
    return [now - timedelta(days=i) for i in range(days)]


def already_done(dt: datetime) -> bool:
    yy = yymmdd(dt)

    candidates = [
        os.path.join(EXTRACT_DIR, f"k{yy}.txt"),
        os.path.join(EXTRACT_DIR, f"K{yy}.TXT"),
        os.path.join(EXTRACT_DIR, f"K{yy}.txt"),
        os.path.join(EXTRACT_DIR, f"k{yy}.TXT"),
    ]

    return any(os.path.exists(p) for p in candidates)


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

    dates = collect_dates()

    success_count = 0
    exists_count = 0
    skip_count = 0

    for dt in dates:
        yy = yymmdd(dt)

        if already_done(dt):
            print(f"exists: k{yy}.txt")
            success_count += 1
            exists_count += 1
            continue

        ok = try_one(dt)
        if ok:
            success_count += 1
        else:
            skip_count += 1

    print(
        f"done: total_days={len(dates)} "
        f"success_count={success_count} "
        f"exists_count={exists_count} "
        f"skip_count={skip_count}"
    )


if __name__ == "__main__":
    main()