import json
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JST = timezone(timedelta(hours=9))

# 24場コード
VENUES = [
    ("01", "桐生"), ("02", "戸田"), ("03", "江戸川"), ("04", "平和島"),
    ("05", "多摩川"), ("06", "浜名湖"), ("07", "蒲郡"), ("08", "常滑"),
    ("09", "津"), ("10", "三国"), ("11", "びわこ"), ("12", "住之江"),
    ("13", "尼崎"), ("14", "鳴門"), ("15", "丸亀"), ("16", "児島"),
    ("17", "宮島"), ("18", "徳山"), ("19", "下関"), ("20", "若松"),
    ("21", "芦屋"), ("22", "福岡"), ("23", "唐津"), ("24", "大村"),
]

# 各場の当日レース一覧（ここが一番判定しやすい）
RACELIST_URL = "https://www.boatrace.jp/owpc/pc/race/racelist"

NO_RACE_PHRASES = [
    "本日のレースはありません",
    "本日はレースを行っておりません",
    "レースはありません",
]

TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
RNO_RE = re.compile(r"\b(1[0-2]|[1-9])R\b")


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; race-data-bot/1.0; +https://github.com/)",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    })
    return s


def parse_racelist(html: str) -> dict:
    """
    racelistページから
    - held（開催中）
    - races: [{rno, close_time}]
    を抽出する
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # 「本日のレースはありません」系が出たら非開催
    if any(p in text for p in NO_RACE_PHRASES):
        return {"held": False, "races": []}

    races = []

    # まずはテーブル行っぽいものから抽出（構造が変わっても row.text で拾えるようにする）
    rows = soup.select("tr")
    for row in rows:
        row_text = row.get_text(" ", strip=True)
        m_rno = RNO_RE.search(row_text)
        if not m_rno:
            continue

        rno = int(m_rno.group(1))

        # 行内の時刻候補を拾って、最後に出てくる時刻を締切として採用（だいたい締切が後ろにある）
        times = TIME_RE.findall(row_text)
        if not times:
            continue

        hh, mm = times[-1]
        close_time = f"{int(hh):02d}:{mm}"

        races.append({"rno": rno, "close_time": close_time})

    # 1〜12Rの重複を整理してソート
    uniq = {}
    for r in races:
        if 1 <= r["rno"] <= 12:
            uniq[r["rno"]] = r["close_time"]

    races_sorted = [{"rno": k, "close_time": uniq[k]} for k in sorted(uniq.keys())]

    # racesが全く取れなかった場合でも、開催ページなのに構造変わった可能性があるので held は True にして返す
    return {"held": True, "races": races_sorted}


def compute_next_race(races: list, now: datetime) -> dict | None:
    """
    「今から次に表示すべき締切」を返す
    - まだ締切前の最小R
    - 全部締切後なら None
    """
    for r in races:
        try:
            hh, mm = map(int, r["close_time"].split(":"))
            close_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if close_dt >= now:
                return {"rno": r["rno"], "close_time": r["close_time"]}
        except Exception:
            continue
    return None


def main():
    now = datetime.now(JST)
    hd = now.strftime("%Y%m%d")  # boatraceは hd=YYYYMMDD がよく通る
    out = {
        "date": now.strftime("%Y-%m-%d"),
        "checked_at": now.isoformat(),
        "held_places": [],
        "venues": [],
    }

    s = make_session()

    for jcd, name in VENUES:
        # 少しだけ間隔（相手に優しい＆429回避）
        time.sleep(0.15)

        params = {"jcd": jcd, "hd": hd}
        res = s.get(RACELIST_URL, params=params, timeout=25)
        res.encoding = "utf-8"

        parsed = parse_racelist(res.text)
        venue_obj = {
            "name": name,
            "jcd": jcd,
            "held": parsed["held"],
            "races": parsed["races"],
        }

        if parsed["held"]:
            out["held_places"].append(name)
            venue_obj["next"] = compute_next_race(parsed["races"], now)

        out["venues"].append(venue_obj)

    # 保存
    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()