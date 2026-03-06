# scripts/fetch_mbrace.py
# mbrace の番組表 lzh を取得して data/extract に展開する
# 出力:
# - data/source_final_url.txt
# - data/download/bYYMMDD.lzh
# - data/extract/bYYMMDD.txt
#
# 方針:
# - 番組表は B 系だけを見る
# - 今日分がまだ出ていない時は失敗にせず、正常終了でスキップする
# - HEAD が通らない環境もあるため GET フォールバック付き

import os
import re
import shutil
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

JST = timezone(timedelta(hours=9))

DATA_DIR = "data"
DOWNLOAD_DIR = os.path.join(DATA_DIR, "download")
EXTRACT_DIR = os.path.join(DATA_DIR, "extract")
SOURCE_URL_PATH = os.path.join(DATA_DIR, "source_final_url.txt")

def ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(EXTRACT_DIR, exist_ok=True)

def yymmdd(dt: datetime) -> str:
    return dt.strftime("%y%m%d")

def yyyymm(dt: datetime) -> str:
    return dt.strftime("%Y%m")

def build_url(dt: datetime) -> str:
    return f"https://www.mbrace.or.jp/od2/B/{yyyymm(dt)}/b{yymmdd(dt)}.lzh"

def url_exists(url: str, timeout: int = 20) -> bool:
    # まず HEAD
    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return 200 <= getattr(res, "status", 200) < 400
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
    except Exception:
        pass

    # HEAD が弾かれるケース用に GET フォールバック
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Range": "bytes=0-0",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return 200 <= getattr(res, "status", 200) < 400
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        return False
    except Exception:
        return False

def download_file(url: str, dest_path: str, timeout: int = 60) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as res, open(dest_path, "wb") as f:
        shutil.copyfileobj(res, f)

def extract_lzh(lzh_path: str, out_dir: str) -> None:
    subprocess.run(
        ["lhasa", "x", "-f", lzh_path],
        cwd=out_dir,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

def find_txt_for_date(out_dir: str, yyMMdd: str) -> Optional[str]:
    exact = os.path.join(out_dir, f"b{yyMMdd}.txt")
    if os.path.exists(exact):
        return exact

    cands = []
    for fn in os.listdir(out_dir):
        if re.fullmatch(rf"b{yyMMdd}\.txt", fn, re.IGNORECASE):
            cands.append(os.path.join(out_dir, fn))
    if cands:
        cands.sort()
        return cands[0]

    return None

def pick_target_url() -> Tuple[Optional[str], Optional[str]]:
    """
    B 系のみを見る。
    優先順:
    1. 今日
    2. 明日
    3. 昨日
    4. 明後日
    5. 一昨日
    見つからなければ (None, None) を返してスキップ。
    """
    now = datetime.now(JST)
    candidates = [
        now,
        now + timedelta(days=1),
        now - timedelta(days=1),
        now + timedelta(days=2),
        now - timedelta(days=2),
    ]

    checked = []
    for dt in candidates:
        url = build_url(dt)
        checked.append(url)
        if url_exists(url):
            return url, yymmdd(dt)

    print("mbrace lzh not found yet")
    print("checked:")
    for url in checked:
        print(" -", url)
    return None, None

def main() -> None:
    ensure_dirs()

    url, yyMMdd = pick_target_url()
    if not url or not yyMMdd:
        print("skip: mbrace file is not published yet")
        return

    lzh_name = f"b{yyMMdd}.lzh"
    lzh_path = os.path.join(DOWNLOAD_DIR, lzh_name)

    download_file(url, lzh_path)

    with open(SOURCE_URL_PATH, "w", encoding="utf-8") as f:
        f.write(url)

    extract_lzh(lzh_path, EXTRACT_DIR)

    txt_path = find_txt_for_date(EXTRACT_DIR, yyMMdd)
    if not txt_path:
        raise FileNotFoundError(f"extracted txt not found for b{yyMMdd}.txt")

    print("source_url:", url)
    print("downloaded:", lzh_path)
    print("extracted_txt:", txt_path)

if __name__ == "__main__":
    main()