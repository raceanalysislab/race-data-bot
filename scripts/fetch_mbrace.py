import json
import time
import requests
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# 場コード（jcd）対応
VENUE_JCD = [
  ("桐生","01"),("戸田","02"),("江戸川","03"),("平和島","04"),("多摩川","05"),("浜名湖","06"),
  ("蒲郡","07"),("常滑","08"),("津","09"),("三国","10"),("びわこ","11"),("住之江","12"),
  ("尼崎","13"),("鳴門","14"),("丸亀","15"),("児島","16"),("宮島","17"),("徳山","18"),
  ("下関","19"),("若松","20"),("芦屋","21"),("福岡","22"),("唐津","23"),("大村","24"),
]

BASE = "https://www.boatrace.jp/owpc/pc/race/raceindex"

# 「開催してない」判定に使う文言（見つかったら held=False）
NOT_HELD_PHRASES = [
    "本日のレースはありません",
    "本日のレースは開催されません",
    "開催はありません",
    "レース情報がありません",
]

def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; race-data-bot/1.0)",
        "Accept-Language": "ja,en;q=0.8",
    })
    return s

def is_held_today(session: requests.Session, jcd: str, yyyymmdd: str) -> bool:
    url = f"{BASE}?jcd={jcd}&hd={yyyymmdd}"
    # 軽いリトライ（タイムアウト/一時エラー対策）
    last_err = None
    for _ in range(3):
        try:
            r = session.get(url, timeout=20)
            r.encoding = "utf-8"
            html = r.text
            # 否定文言があれば未開催
            for p in NOT_HELD_PHRASES:
                if p in html:
                    return False
            # 否定が見つからなければ開催扱い（※ここが一番強い）
            return True
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    # 3回失敗したら「不明」ではなく安全側で False
    return False

def main():
    now = datetime.now(JST)
    yyyymmdd = now.strftime("%Y%m%d")

    session = get_session()

    held_places = []
    venues = []
    for name, jcd in VENUE_JCD:
        held = is_held_today(session, jcd, yyyymmdd)
        if held:
            held_places.append(name)
        venues.append({"name": name, "jcd": jcd, "held": held})

    out = {
        "date": now.strftime("%Y-%m-%d"),
        "checked_at": now.isoformat(timespec="seconds"),
        "held_places": held_places,
        "venues": venues,
    }

    # data/ が無い場合でも落ちないように（Actionsで確実に動く）
    import os
    os.makedirs("data", exist_ok=True)

    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()