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
    with urllib.request.urlopen(req, timeout=timeout)