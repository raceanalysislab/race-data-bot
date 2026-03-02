import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))

URL = "https://www.boatrace.jp/owpc/pc/race/index"

ALL_VENUES = [
    "桐生","戸田","江戸川","平和島","多摩川","浜名湖","蒲郡","常滑",
    "津","三国","びわこ","住之江","尼崎","鳴門","丸亀","児島",
    "宮島","徳山","下関","若松","芦屋","福岡","唐津","大村"
]

OUT_PATH = "data/venues_today.json"


def build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def fetch_html(session: requests.Session) -> str:
    headers = {
        # これがないと弾かれたり遅くなったりしがち
        "User-Agent": "Mozilla/5.0 (GitHubActions; race-data-bot)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Connection": "close",
    }

    # timeout を (接続, 読み取り) で長めに
    r = session.get(URL, headers=headers, timeout=(10, 60))
    # 429/5xx は Retry が面倒見てくれるが、最終的にダメならここで落とす
    r.raise_for_status()

    # 文字化け対策（サイト側が厳密にcharset返さないことがある）
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def main():
    now = datetime.now(JST)

    session = build_session()

    # 念のため「ワンチャン詰まる」ケースも拾う（Retryに加えて最終保険）
    last_err = None
    for attempt in range(1, 4):
        try:
            html = fetch_html(session)
            last_err = None
            break
        except Exception as e:
            last_err = e
            # 1回目→2回目→3回目で待ち時間を増やす
            time.sleep(2 * attempt)

    if last_err is not None:
        # ここで落ちる＝Actionsのログに原因が出る
        raise last_err

    soup = BeautifulSoup(html, "html.parser")

    # 開催してる場だけこのclassに出る（サイト側の構造が変わると空になる）
    held_nodes = soup.select(".is-place")
    held_today = [n.get_text(strip=True) for n in held_nodes if n.get_text(strip=True)]

    venues = [{"name": v, "held": (v in held_today)} for v in ALL_VENUES]

    payload = {
        "date": now.strftime("%Y-%m-%d"),
        "held_places": held_today,
        "venues": venues,
    }

    write_json_atomic(OUT_PATH, payload)


if __name__ == "__main__":
    main()