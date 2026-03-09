import csv
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

INDEX_URL = "https://www1.mbrace.or.jp/od2/K/dindex.html"
OUT_PATH = Path("data/site/players.json")


def fetch_text(url: str) -> str:
    r = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
        },
    )
    r.raise_for_status()
    return r.text


def fetch_bytes(url: str) -> bytes:
    r = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
        },
    )
    r.raise_for_status()
    return r.content


def extract_links(html: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    return [urljoin(INDEX_URL, h) for h in hrefs]


def pick_player_url(links: list[str]) -> str:
    candidates = []
    for link in links:
        low = link.lower()
        if "player" in low and (low.endswith(".csv") or low.endswith(".lzh") or low.endswith(".zip")):
            candidates.append(link)

    if not candidates:
        raise RuntimeError("選手データらしい配布ファイルURLが見つかりませんでした。")

    # csv優先
    candidates.sort(key=lambda x: (0 if x.lower().endswith(".csv") else 1, x))
    print("player candidates:")
    for c in candidates:
        print(" -", c)
    return candidates[0]


def decode_text(data: bytes) -> str:
    for enc in ("shift_jis", "cp932", "utf-8-sig", "utf-8"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("shift_jis", errors="ignore")


def normalize_key(s: str) -> str:
    return str(s or "").strip().replace(" ", "").replace("　", "")


def pick(row: dict, *keys: str) -> str:
    normalized = {normalize_key(k): v for k, v in row.items()}
    for key in keys:
        val = normalized.get(normalize_key(key))
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return ""


def parse_csv(data: bytes) -> dict:
    text = decode_text(data)
    reader = csv.DictReader(text.splitlines())

    if not reader.fieldnames:
        raise RuntimeError("CSVヘッダが見つかりません。")

    players = {}

    for row in reader:
        regno = pick(row, "登録番号", "登番", "選手登録番号")
        if not regno:
            continue

        players[str(regno)] = {
            "name": pick(row, "選手名", "名前"),
            "grade": pick(row, "級別", "級"),
            "branch": pick(row, "支部"),
            "age": pick(row, "年齢"),
            "avg_st": pick(row, "平均ST", "平均スタートタイミング", "平均スタート"),
            "nat_win": pick(row, "全国勝率"),
            "local_win": pick(row, "当地勝率"),
        }

    if not players:
        headers = ", ".join(reader.fieldnames[:20])
        raise RuntimeError(f"players が 0 件です。headers={headers}")

    return players


def save_json(players: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
    print(f"saved: {OUT_PATH}")
    print(f"players: {len(players)}")


def main() -> None:
    print(f"downloading index: {INDEX_URL}")
    html = fetch_text(INDEX_URL)

    links = extract_links(html)
    player_url = pick_player_url(links)
    print(f"selected: {player_url}")

    if not player_url.lower().endswith(".csv"):
        raise RuntimeError(
            "見つかったのがCSV直ファイルではありません。"
            "まず候補URLをログで確認してください。"
        )

    data = fetch_bytes(player_url)
    players = parse_csv(data)
    save_json(players)


if __name__ == "__main__":
    main()