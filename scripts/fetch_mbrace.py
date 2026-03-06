# scripts/fetch_mbrace.py
# mbrace の番組表 lzh を取得して data/extract に展開する
# 出力:
# - data/source_final_url.txt
# - data/download/bYYMMDD.lzh
# - data/extract/bYYMMDD.txt
#
# 方針:
# - 番組表は B 系のみを見る
# - 今日分を最優先で取りに行く
# - HEAD 判定に頼らず、実際に GET して検証する
# - 404 HTML や壊れた LZH を自動で弾く
# - 解凍は一時ディレクトリで行い、成功した txt だけを data/extract に移す
# - 今日分が未公開なら失敗にせず正常終了でスキップする

import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List

JST = timezone(timedelta(hours=9))

DATA_DIR = "data"
DOWNLOAD_DIR = os.path.join(DATA_DIR, "download")
EXTRACT_DIR = os.path.join(DATA_DIR, "extract")
SOURCE_URL_PATH = os.path.join(DATA_DIR, "source_final_url.txt")

USER_AGENT = "Mozilla/5.0"

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

def candidate_dates() -> List[datetime]:
    now = datetime.now(JST)
    # 当日最優先。その次に翌日、前日。
    # 深夜またぎや公開タイミングのズレ対策で近傍も見る。
    return [
        now,
        now + timedelta(days=1),
        now - timedelta(days=1),
        now + timedelta(days=2),
        now - timedelta(days=2),
    ]

def download_file(url: str, dest_path: str, timeout: int = 60) -> None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res, open(dest_path, "wb") as f:
        shutil.copyfileobj(res, f)

def looks_like_html(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(512).lower()
        return (
            b"<html" in head
            or b"<!doctype html" in head
            or b"<head" in head
            or b"not found" in head
        )
    except Exception:
        return False

def extract_lzh_to_temp(lzh_path: str) -> str:
    temp_dir = tempfile.mkdtemp(prefix="mbrace_extract_")
    result = subprocess.run(
        ["lhasa", "x", os.path.abspath(lzh_path)],
        cwd=temp_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"lhasa extract failed: returncode={result.returncode}")

    return temp_dir

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

def move_txt_to_extract(temp_dir: str, yyMMdd: str) -> str:
    txt_path = find_txt_for_date(temp_dir, yyMMdd)
    if not txt_path:
        txt_files = sorted(
            [
                os.path.join(temp_dir, fn)
                for fn in os.listdir(temp_dir)
                if fn.lower().endswith(".txt")
            ]
        )
        if len(txt_files) == 1:
            txt_path = txt_files[0]

    if not txt_path:
        raise FileNotFoundError(f"extracted txt not found for b{yyMMdd}.txt")

    dst_path = os.path.join(EXTRACT_DIR, f"b{yyMMdd}.txt")
    shutil.copy2(txt_path, dst_path)
    return dst_path

def try_one(dt: datetime) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    yyMMdd = yymmdd(dt)
    url = build_url(dt)
    lzh_name = f"b{yyMMdd}.lzh"
    lzh_path = os.path.join(DOWNLOAD_DIR, lzh_name)

    print("try:", url)

    try:
        download_file(url, lzh_path)
    except urllib.error.HTTPError as e:
        print(f"http error: {e.code} {url}")
        return False, None, None, None
    except Exception as e:
        print(f"download error: {url} {e}")
        return False, None, None, None

    if not os.path.exists(lzh_path):
        print(f"missing downloaded file: {lzh_path}")
        return False, None, None, None

    size = os.path.getsize(lzh_path)
    if size == 0:
        print(f"empty lzh: {lzh_path}")
        return False, None, None, None

    if looks_like_html(lzh_path):
        print(f"downloaded html instead of lzh: {lzh_path}")
        return False, None, None, None

    temp_dir = None
    try:
        temp_dir = extract_lzh_to_temp(lzh_path)
        txt_path = move_txt_to_extract(temp_dir, yyMMdd)
    except Exception as e:
        print(f"extract error: {url} {e}")
        return False, None, None, None
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    with open(SOURCE_URL_PATH, "w", encoding="utf-8") as f:
        f.write(url)

    return True, url, lzh_path, txt_path

def main() -> None:
    ensure_dirs()

    for dt in candidate_dates():
        ok, url, lzh_path, txt_path = try_one(dt)
        if ok:
            print("source_url:", url)
            print("downloaded:", lzh_path)
            print("downloaded_size:", os.path.getsize(lzh_path))
            print("extracted_txt:", txt_path)
            return

    print("skip: mbrace file is not published yet")

if __name__ == "__main__":
    main()