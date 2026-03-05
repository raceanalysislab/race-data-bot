# scripts/fetch_mbrace.py
# mbrace: 番組表(lzh)をダウンロード → data/today.lzh → data/extract/ 解凍
# その日の bYYMMDD.txt を必ず作る

import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))

DATA_DIR = "data"
LZH_PATH = os.path.join(DATA_DIR, "today.lzh")
EXTRACT_DIR = os.path.join(DATA_DIR, "extract")

DEFAULT_BASE = "https://www1.mbrace.or.jp/od2/B"


def jst_now() -> datetime:
    return datetime.now(JST)


def yymmdd(now: datetime) -> str:
    return now.strftime("%y%m%d")


def yyyymm(now: datetime) -> str:
    return now.strftime("%Y%m")


def build_url(now: datetime) -> str:
    return f"{DEFAULT_BASE}/{yyyymm(now)}/b{yymmdd(now)}.lzh"


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www1.mbrace.or.jp/",
    })

    retry = Retry(
        total=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )

    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def download(url: str, out_path: str) -> int:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    s = make_session()
    r = s.get(url, timeout=30)
    r.raise_for_status()

    content_type = (r.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        raise RuntimeError(f"Downloaded HTML instead of lzh: {url}")

    with open(out_path, "wb") as f:
        f.write(r.content)

    size = os.path.getsize(out_path)
    if size <= 0:
        raise RuntimeError("Downloaded file empty")

    return size


def ensure_extract_dir(clean=True):
    os.makedirs(EXTRACT_DIR, exist_ok=True)

    if clean:
        for f in os.listdir(EXTRACT_DIR):
            p = os.path.join(EXTRACT_DIR, f)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
            except:
                pass


def run_extract(cmd):
    return subprocess.run(cmd, cwd=EXTRACT_DIR, capture_output=True, text=True)


def extract_lzh(path: str):

    ensure_extract_dir(True)

    abs_lzh = os.path.abspath(path)

    candidates = [
        ["lhasa", "x", "-f", abs_lzh],
        ["lhasa", "-x", "-f", abs_lzh],
        ["lhasa", "-x", abs_lzh],
        ["lha", "x", abs_lzh],
    ]

    last = None

    for cmd in candidates:
        try:
            p = run_extract(cmd)
            last = p
            if p.returncode == 0:
                return
        except FileNotFoundError:
            continue

    raise RuntimeError(
        "extract failed\n"
        f"stdout:\n{last.stdout}\n"
        f"stderr:\n{last.stderr}"
    )


def find_extracted_txt() -> Optional[str]:

    if not os.path.isdir(EXTRACT_DIR):
        return None

    cands = [f for f in os.listdir(EXTRACT_DIR) if f.endswith(".txt")]

    if not cands:
        return None

    cands.sort()

    return os.path.join(EXTRACT_DIR, cands[0])


def align_today_txt(now: datetime) -> Optional[str]:

    src = find_extracted_txt()

    if not src:
        return None

    target = os.path.join(EXTRACT_DIR, f"b{yymmdd(now)}.txt")

    if os.path.abspath(src) == os.path.abspath(target):
        return target

    shutil.copyfile(src, target)

    return target


def main():

    now = jst_now()

    url = build_url(now)

    print("[mbrace] url:", url)

    size = download(url, LZH_PATH)

    print("[mbrace] downloaded:", size)

    extract_lzh(LZH_PATH)

    print("[mbrace] extracted")

    aligned = align_today_txt(now)

    print("[mbrace] aligned txt:", aligned)

    if not aligned:
        raise RuntimeError("txt not found after extract")


if __name__ == "__main__":
    main()