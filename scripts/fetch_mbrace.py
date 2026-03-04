# scripts/fetch_mbrace.py
# mbrace: 番組表(lzh)をダウンロード → data/today.lzh に保存 → data/extract/ に解凍
# 依存: GitHub Actionsで `sudo apt-get install -y lhasa` 済み想定

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

SOURCE_FINAL_URL_TXT = os.path.join(DATA_DIR, "source_final_url.txt")

# mbraceの例:
# https://www1.mbrace.or.jp/od2/B/202603/b260303.lzh
DEFAULT_BASE = "https://www1.mbrace.or.jp/od2/B"


def jst_now() -> datetime:
    return datetime.now(JST)


def yymmdd(now: datetime) -> str:
    return now.strftime("%y%m%d")


def yyyymm(now: datetime) -> str:
    return now.strftime("%Y%m")


def build_guess_url(now: datetime) -> str:
    return f"{DEFAULT_BASE}/{yyyymm(now)}/b{yymmdd(now)}.lzh"


def read_source_final_url() -> Optional[str]:
    if not os.path.exists(SOURCE_FINAL_URL_TXT):
        return None
    try:
        with open(SOURCE_FINAL_URL_TXT, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("http"):
                    return s
    except Exception:
        return None
    return None


def write_source_final_url(url: str) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SOURCE_FINAL_URL_TXT, "w", encoding="utf-8") as f:
        f.write(url.strip() + "\n")


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

    # 0バイト/HTML混入ガード（たまにエラーページが返る）
    content_type = (r.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        raise RuntimeError(f"Downloaded HTML instead of lzh: {url}")

    with open(out_path, "wb") as f:
        f.write(r.content)
    return len(r.content)


def ensure_extract_dir() -> None:
    os.makedirs(EXTRACT_DIR, exist_ok=True)


def extract_lzh(lzh_path: str) -> None:
    """
    lhasaで解凍。解凍先は data/extract/
    """
    ensure_extract_dir()

    # 念のため古いゴミを残しつつ上書きOK（必要ならここで掃除してもいい）
    # ここは「今のやり方は変えず」なので削除はしない。

    # lhasa は作業ディレクトリに解凍するので cwd を extract にする
    # -f: 強制上書き / x: extract
    cmd = ["lhasa", "x", "-f", os.path.abspath(lzh_path)]
    p = subprocess.run(cmd, cwd=EXTRACT_DIR, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            "lhasa failed\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{p.stdout}\n"
            f"stderr:\n{p.stderr}\n"
        )


def find_extracted_txt() -> Optional[str]:
    """
    data/extract 配下から bYYMMDD.txt に相当するtxtを探す
    """
    if not os.path.isdir(EXTRACT_DIR):
        return None

    # txt候補を広めに拾う
    cands = []
    for fn in os.listdir(EXTRACT_DIR):
        if fn.lower().endswith(".txt"):
            cands.append(fn)

    # b******.txt を優先
    cands.sort(key=lambda x: (0 if re.match(r"^b\d{6}\.txt$", x, re.IGNORECASE) else 1, x))
    if not cands:
        return None
    return os.path.join(EXTRACT_DIR, cands[0])


def align_today_txt(now: datetime) -> Optional[str]:
    """
    解凍された txt を data/extract/bYYMMDD.txt に揃える
    """
    src = find_extracted_txt()
    if not src:
        return None

    target_name = f"b{yymmdd(now)}.txt"
    dst = os.path.join(EXTRACT_DIR, target_name)

    # 既に同名なら何もしない
    if os.path.abspath(src) == os.path.abspath(dst):
        return dst

    # 同名が既にある場合は上書き
    shutil.copyfile(src, dst)
    return dst


def main():
    now = jst_now()

    # 1) URL決定（既存のsource_final_url.txtを最優先）
    url = read_source_final_url()
    if not url:
        url = build_guess_url(now)
        # 推測URLも保存しておく（次回以降の安定化）
        write_source_final_url(url)

    print("[mbrace] url:", url)

    # 2) ダウンロード
    size = download(url, LZH_PATH)
    print("[mbrace] downloaded:", LZH_PATH, "bytes=", size)

    # 3) 解凍（data/extract を必ず作る）
    extract_lzh(LZH_PATH)
    print("[mbrace] extracted into:", EXTRACT_DIR)

    # 4) txt名を揃える（parse側が参照しやすいように）
    aligned = align_today_txt(now)
    print("[mbrace] aligned txt:", aligned if aligned else "(not found)")

    # extractが無い問題を潰すため、ここで最終チェック
    if not os.path.isdir(EXTRACT_DIR):
        raise RuntimeError("extract dir not created")
    if aligned is None:
        # 解凍できてるのにtxtが無い場合は、解凍されたファイル一覧を出す
        files = os.listdir(EXTRACT_DIR)
        raise RuntimeError(f"no txt found under {EXTRACT_DIR}. files={files}")


if __name__ == "__main__":
    main()