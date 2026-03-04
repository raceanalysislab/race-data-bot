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

# 例: https://www1.mbrace.or.jp/od2/B/202603/b260303.lzh
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

    # HTMLが返ってきたら落とす（エラーページ対策）
    content_type = (r.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        raise RuntimeError(f"Downloaded HTML instead of lzh: {url}")

    with open(out_path, "wb") as f:
        f.write(r.content)
    return len(r.content)


def ensure_clean_extract_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    # -f を使わずに確実に上書きするため、extract配下だけ掃除する
    os.makedirs(EXTRACT_DIR, exist_ok=True)
    for fn in os.listdir(EXTRACT_DIR):
        p = os.path.join(EXTRACT_DIR, fn)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        except Exception:
            pass


def extract_lzh(lzh_path: str) -> None:
    """
    lhasaで解凍。解凍先は data/extract/
    ※ lhasa は「-x」オプション形式。 'lhasa x -f' はNG。
    """
    ensure_clean_extract_dir()

    # lhasaは作業ディレクトリ(cwd)に解凍するので cwd=EXTRACT_DIR
    # -x: extract
    cmd = ["lhasa", "-x", os.path.abspath(lzh_path)]
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
    data/extract 配下から txt を探す（b******.txt優先）
    """
    if not os.path.isdir(EXTRACT_DIR):
        return None

    cands = [fn for fn in os.listdir(EXTRACT_DIR) if fn.lower().endswith(".txt")]
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

    if os.path.abspath(src) == os.path.abspath(dst):
        return dst

    shutil.copyfile(src, dst)
    return dst


def main():
    now = jst_now()

    # 1) URL決定（source_final_url.txt優先）
    url = read_source_final_url()
    if not url:
        url = build_guess_url(now)
        write_source_final_url(url)

    print("[mbrace] url:", url)

    # 2) ダウンロード
    size = download(url, LZH_PATH)
    print("[mbrace] downloaded:", LZH_PATH, "bytes=", size)

    # 3) 解凍
    extract_lzh(LZH_PATH)
    print("[mbrace] extracted into:", EXTRACT_DIR)

    # 4) txt名を揃える
    aligned = align_today_txt(now)
    print("[mbrace] aligned txt:", aligned if aligned else "(not found)")

    if aligned is None:
        files = os.listdir(EXTRACT_DIR) if os.path.isdir(EXTRACT_DIR) else []
        raise RuntimeError(f"no txt found under {EXTRACT_DIR}. files={files}")


if __name__ == "__main__":
    main()