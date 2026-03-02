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

# 開催っぽい印（文字化け/全角を正規化した後に見る）
HELD_MARK_RE = re.compile(r'(第\s*\d+\s*日|初日|最終日|(?<!\d)0?1R(?!\d))')

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

def normalize_text(s: str) -> str:
    # 全角英数→半角
    def fw_to_hw(ch):
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:
            return chr(o - 0xFEE0)
        return ch
    s = "".join(fw_to_hw(c) for c in s)

    # よくある揺れを統一
    s = s.replace("Ｒ", "R").replace("ｒ", "r").replace("ｒ", "r")
    s = s.replace("\u3000", " ")  # 全角スペース
    s = re.sub(r"[ \t]+", " ", s)
    return s

def build_blocks(text: str):
    """
    会場名の出現位置を全部拾って、出現順に「会場ブロック」を切り出す。
    """
    positions = []
    for v in VENUES:
        name = v["name"]
        idx = text.find(name)
        if idx >= 0:
            positions.append((idx, name))
    positions.sort()

    blocks = {}
    for i, (idx, name) in enumerate(positions):
        end = positions[i+1][0] if i+1 < len(positions) else len(text)
        blocks[name] = text[idx:end]
    return blocks

def pick_best_text(outdir: str) -> tuple[str, str]:
    """
    解凍後のファイルから、会場名が一番多く含まれるテキストを選ぶ。
    """
    venue_names = [v["name"] for v in VENUES]
    best_path, best_score, best_text = None, -1, ""

    for root, _, files in os.walk(outdir):
        for fn in files:
            p = os.path.join(root, fn)
            try:
                b = open(p, "rb").read()
            except Exception:
                continue
            t = normalize_text(safe_decode(b))
            score = sum(1 for nm in venue_names if nm in t)
            if score > best_score:
                best_score = score
                best_path = p
                best_text = t

    if not best_path or best_score <= 0:
        raise RuntimeError("解凍後、会場名が含まれるファイルが見つからない")

    return best_path, best_text

def main():
    os.makedirs("data", exist_ok=True)

    t = now()
    yyyymm = t.strftime("%Y%m")
    today_dd = t.strftime("%d")

    dmenu_html = fetch_text(DMENU)
    with open("data/source_dmenu.html", "w", encoding="utf-8") as f:
        f.write(dmenu_html)

    m = MONTH_RE.search(dmenu_html)
    if m:
        yyyymm = m.group(1)

    mday_url = f"{BASE}{yyyymm}/mday.html"
    mday_html = fetch_text(mday_url)
    with open("data/source_mday.html", "w", encoding="utf-8") as f:
        f.write(mday_html)

    d = DIR_RE.search(mday_html)
    if not d:
        raise RuntimeError("mday.html から dir が取れない")

    dir_path = d.group(1)

    days = DAY_RE.findall(mday_html)
    if not days:
        raise RuntimeError("mday.html から日付が取れない")

    dd = today_dd if today_dd in days else sorted(days)[-1]

    lzh_url = "https://www1.mbrace.or.jp" + dir_path + dd + ".lzh"
    with open("data/source_final_url.txt", "w", encoding="utf-8") as f:
        f.write(lzh_url)

    r = requests.get(lzh_url, timeout=60, headers=HEADERS)
    if r.status_code != 200 or not r.content:
        raise RuntimeError(f"lzh が取れない: {r.status_code}")

    lzh_path = "data/today.lzh"
    with open(lzh_path, "wb") as f:
        f.write(r.content)

    outdir = "data/extract"
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)

    archive_abs = os.path.abspath(lzh_path)
    subprocess.run(["lhasa", "-x", archive_abs], cwd=outdir, check=True)

    best_path, best_text = pick_best_text(outdir)

    # デバッグ保存
    with open("data/source_venues.txt", "w", encoding="utf-8") as f:
        f.write(best_text)
    with open("data/source_venues_path.txt", "w", encoding="utf-8") as f:
        f.write(best_path)

    blocks = build_blocks(best_text)

    venues = []
    for v in VENUES:
        name = v["name"]
        block = blocks.get(name, "")
        held = bool(block) and bool(HELD_MARK_RE.search(block))
        venues.append({
            "jcd": v["jcd"],
            "name": name,
            "held": held,
            "bytes": len(best_text),
            "score_file": os.path.basename(best_path),
        })

    with open("data/today.json", "w", encoding="utf-8") as f:
        json.dump({
            "date": t.strftime("%Y-%m-%d"),
            "updated_at": t.strftime("%H:%M"),
            "yyyymm": yyyymm,
            "dd_used": dd,
            "source_file": os.path.basename(best_path),
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