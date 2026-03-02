import os
import re
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
import requests

JST = timezone(timedelta(hours=9))

VENUES = [
  {"jcd":"01","name":"桐生"}, {"jcd":"02","name":"戸田"}, {"jcd":"03","name":"江戸川"}, {"jcd":"04","name":"平和島"},
  {"jcd":"05","name":"多摩川"}, {"jcd":"06","name":"浜名湖"}, {"jcd":"07","name":"蒲郡"}, {"jcd":"08","name":"常滑"},
  {"jcd":"09","name":"津"}, {"jcd":"10","name":"三国"}, {"jcd":"11","name":"びわこ"}, {"jcd":"12","name":"住之江"},
  {"jcd":"13","name":"尼崎"}, {"jcd":"14","name":"鳴門"}, {"jcd":"15","name":"丸亀"}, {"jcd":"16","name":"児島"},
  {"jcd":"17","name":"宮島"}, {"jcd":"18","name":"徳山"}, {"jcd":"19","name":"下関"}, {"jcd":"20","name":"若松"},
  {"jcd":"21","name":"芦屋"}, {"jcd":"22","name":"福岡"}, {"jcd":"23","name":"唐津"}, {"jcd":"24","name":"大村"},
]

BASE = "https://www1.mbrace.or.jp/od2/B/"
DMENU = BASE + "dmenu.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

MONTH_RE = re.compile(r'<OPTION\s+VALUE="(20\d{4})"\s*>', re.IGNORECASE)
DIR_RE   = re.compile(r'var\s+dir\s*=\s*"([^"]+)"', re.IGNORECASE)
DAY_RE   = re.compile(r'NAME="MDAY"\s+VALUE="(\d{2})"', re.IGNORECASE)

# ✅ Kファイル（開催一覧）を優先して拾う
KFILE_RE = re.compile(r'^[Kk].*\.txt$')

def now():
    return datetime.now(JST)

def fetch_text(url: str) -> str:
    r = requests.get(url, timeout=30, headers=HEADERS)
    r.encoding = r.apparent_encoding
    return r.text

def safe_decode(b: bytes) -> str:
    for enc in ("cp932", "shift_jis", "euc_jp", "utf-8"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("latin1", errors="ignore")

def main():
    os.makedirs("data", exist_ok=True)

    t = now()
    yyyymm = t.strftime("%Y%m")
    today_dd = t.strftime("%d")  # 01-31

    # 1) dmenu.html 保存（デバッグ用）
    dmenu_html = fetch_text(DMENU)
    with open("data/source_dmenu.html", "w", encoding="utf-8") as f:
        f.write(dmenu_html)

    # 2) dmenu から最新月を拾う（あれば優先）
    m = MONTH_RE.search(dmenu_html)
    if m:
        yyyymm = m.group(1)

    # 3) その月の mday.html を取得して dir を抜く
    mday_url = f"{BASE}{yyyymm}/mday.html"
    mday_html = fetch_text(mday_url)
    with open("data/source_mday.html", "w", encoding="utf-8") as f:
        f.write(mday_html)

    d = DIR_RE.search(mday_html)
    if not d:
        raise RuntimeError("mday.html から dir が取れない（DIR_RE がヒットしない）")

    dir_path = d.group(1)  # /od2/B/202603/b2603

    # 4) mday.htmlに存在する日付を拾って、今日がなければ最後の開催日に寄せる（404回避）
    days = DAY_RE.findall(mday_html)
    if not days:
        raise RuntimeError("mday.html から日付が取れない（DAY_RE がヒットしない）")

    if today_dd in days:
        dd = today_dd
    else:
        dd = sorted(days)[-1]

    # 5) 当日の lzh を取る
    lzh_url = "https://www1.mbrace.or.jp" + dir_path + dd + ".lzh"
    with open("data/source_final_url.txt", "w", encoding="utf-8") as f:
        f.write(lzh_url)

    r = requests.get(lzh_url, timeout=60, headers=HEADERS)
    if r.status_code != 200 or not r.content:
        raise RuntimeError(f"lzh が取れない: {r.status_code}")

    lzh_path = "data/today.lzh"
    with open(lzh_path, "wb") as f:
        f.write(r.content)

    # 6) 解凍（overwriteで止まらないように extract を毎回作り直す）
    outdir = "data/extract"
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)

    archive_abs = os.path.abspath(lzh_path)
    subprocess.run(["lhasa", "-x", archive_abs], cwd=outdir, check=True)

    # 7) ✅ Kファイル（開催一覧）を探す（最優先）
    k_path = None
    for root, _, files in os.walk(outdir):
        for fn in files:
            if KFILE_RE.match(fn):
                k_path = os.path.join(root, fn)
                break
        if k_path:
            break

    # Kが無い場合のみ、保険で「会場名が多いファイル」を使う
    best_path = None
    best_score = -1
    venue_names = [v["name"] for v in VENUES]

    if not k_path:
        for root, _, files in os.walk(outdir):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    b = open(p, "rb").read()
                except Exception:
                    continue
                text = safe_decode(b)
                score = sum(1 for name in venue_names if name in text)
                if score > best_score:
                    best_score = score
                    best_path = p

        if not best_path or best_score <= 0:
            with open("data/extract_list.txt", "w", encoding="utf-8") as f:
                for root, _, files in os.walk(outdir):
                    for fn in files:
                        f.write(os.path.join(root, fn) + "\n")
            raise RuntimeError("解凍後、Kファイルも候補ファイルも見つからない")

        src_path = best_path
    else:
        src_path = k_path

    raw = open(src_path, "rb").read()
    text = safe_decode(raw)

    # デバッグ保存
    with open("data/source_venues.txt", "w", encoding="utf-8") as f:
        f.write(text)
    with open("data/source_venues_path.txt", "w", encoding="utf-8") as f:
        f.write(src_path)

    # ✅ 開催判定：Kファイルは「開催場だけ」が載る前提なので「名前があるか」だけでOK
    venues = []
    for v in VENUES:
        held = (v["name"] in text)
        venues.append({
            "jcd": v["jcd"],
            "name": v["name"],
            "held": held,
            "bytes": len(text),
            "score_file": os.path.basename(src_path),
        })

    with open("data/today.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": t.strftime("%Y-%m-%d"),
            "updated_at": t.strftime("%H:%M"),
            "yyyymm": yyyymm,
            "dd_used": dd,
            "source_file": os.path.basename(src_path),
            "venues": venues
        }, f, ensure_ascii=False, indent=2)

    with open("data/venues_today.json", "w", encoding="utf-8") as f:
        json.dump({
            "time": t.strftime("%Y-%m-%d %H:%M"),
            "venues": venues
        }, f, ensure_ascii=False, indent=2)

    with open("data/picks_today.json", "w", encoding="utf-8") as f:
        json.dump({"time": t.strftime("%Y-%m-%d %H:%M"), "picks": []}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()