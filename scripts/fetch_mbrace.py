import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
INDEX_URL = "https://www.boatrace.jp/owpc/pc/race/index"

# 公式の場コード（jcd）
JCD_MAP = {
  "桐生":"01","戸田":"02","江戸川":"03","平和島":"04","多摩川":"05","浜名湖":"06","蒲郡":"07","常滑":"08",
  "津":"09","三国":"10","びわこ":"11","住之江":"12","尼崎":"13","鳴門":"14","丸亀":"15","児島":"16",
  "宮島":"17","徳山":"18","下関":"19","若松":"20","芦屋":"21","福岡":"22","唐津":"23","大村":"24"
}

def _parse_hhmm_to_dt(hhmm: str, base_date: datetime) -> datetime | None:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", hhmm)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    return base_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

def _fetch_race_deadlines(session: requests.Session, jcd: str, date_yyyymmdd: str) -> list[dict]:
    """
    raceindexページから 1R〜12R の締切時刻を拾う（見つからなければ空）
    """
    url = f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={jcd}&hd={date_yyyymmdd}"
    r = session.get(url, timeout=30)
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")

    deadlines = []
    # 「締切」表記がページ内に複数出るので、"締切" の近辺から hh:mm を拾う方式（DOM変更に強い）
    text = soup.get_text("\n", strip=True)

    # 例: "1R 締切 10:58" みたいな並びが混ざるので幅広く拾う
    # race_no と hh:mm をペアで抜く
    pattern = re.compile(r"(\d{1,2})R.*?締切.*?(\d{1,2}:\d{2})")
    for m in pattern.finditer(text):
        race_no = int(m.group(1))
        hhmm = m.group(2)
        deadlines.append({"race": race_no, "cutoff": hhmm})

    # 同じものが重複することがあるので raceでユニーク化（最後を採用）
    uniq = {}
    for d in deadlines:
        uniq[d["race"]] = d
    return [uniq[k] for k in sorted(uniq.keys())]

def main():
    now = datetime.now(JST)
    date_yyyymmdd = now.strftime("%Y%m%d")

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; race-data-bot/1.0; +https://github.com/)",
        "Accept-Language": "ja,en;q=0.8",
    })

    # ① まず index を踏んで cookie を作る（直アクセス弾き対策）
    res = s.get(INDEX_URL, timeout=30)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    # ② 「本日のレース」表から開催場を拾う
    held_today = []
    for tr in soup.select("table tbody tr"):
        # 1列目に場名が入ってる（th/tdどちらでも）
        first = tr.find(["th", "td"])
        if not first:
            continue
        name = first.get_text(strip=True)
        if name in JCD_MAP:
            held_today.append(name)

    held_today = list(dict.fromkeys(held_today))  # 重複排除（順序維持）

    venues = []
    for name, jcd in JCD_MAP.items():
        held = name in held_today

        next_race = None
        next_cutoff_iso = None

        if held:
            deadlines = _fetch_race_deadlines(s, jcd, date_yyyymmdd)
            # 今より先の締切を探す（= 1R締切後なら2Rに自動で移る）
            for d in deadlines:
                dt_cut = _parse_hhmm_to_dt(d["cutoff"], now)
                if dt_cut and dt_cut > now:
                    next_race = d["race"]
                    next_cutoff_iso = dt_cut.isoformat()
                    break

        venues.append({
            "name": name,
            "jcd": jcd,
            "held": held,
            "next_race": next_race,            # 例: 2
            "next_cutoff": next_cutoff_iso     # 例: "2026-03-03T10:58:00+09:00"
        })

    out = {
        "date": now.strftime("%Y-%m-%d"),
        "checked_at": now.isoformat(),
        "held_places": held_today,
        "venues": venues
    }

    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()