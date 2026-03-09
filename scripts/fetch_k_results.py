import os
import requests
import subprocess
from datetime import datetime

BASE = "https://www1.mbrace.or.jp/od2/K/"

DOWNLOAD_DIR = "data/download_k"
EXTRACT_DIR = "data/extract_k"


def ensure_dirs():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(EXTRACT_DIR, exist_ok=True)


def fetch(url, path):
    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=60,
    )
    r.raise_for_status()

    with open(path, "wb") as f:
        f.write(r.content)


def extract(lzh_path):
    subprocess.run(
        ["lhasa", "x", lzh_path],
        cwd=EXTRACT_DIR,
        check=True,
    )


def main():
    ensure_dirs()

    today = datetime.now()
    yymmdd = today.strftime("%y%m%d")

    url = f"{BASE}k{yymmdd}.lzh"

    lzh_path = f"{DOWNLOAD_DIR}/k{yymmdd}.lzh"

    print("fetch:", url)

    fetch(url, lzh_path)

    print("downloaded:", lzh_path)

    extract(lzh_path)

    print("extracted to:", EXTRACT_DIR)


if __name__ == "__main__":
    main()