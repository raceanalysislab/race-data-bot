import csv
import json
import requests
from pathlib import Path

# ここは「ダウンロードページ」ではなく、
# 実際のデータファイルURLに差し替えること。
# いまの official download ページURLを入れると HTML が返って {} になる。
DATA_URL = "https://www.boatrace.jp/owpc/pc/extra/data/download.html"

OUT_PATH = Path("data/site/players.json")


def fetch_bytes(url: str) -> tuple[bytes, str]:
    print(f"downloading: {url}")
    r = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
        },
    )
    r.raise_for_status()
    content_type = r.headers.get("Content-Type", "")
    return r.content, content_type


def ensure_not_html(data: bytes, content_type: str) -> None:
    head = data[:500].decode("utf-8", errors="ignore").lower()

    if "text/html" in content_type.lower() or "<html" in head or "<!doctype html" in head:
        raise RuntimeError(
            "HTMLページを取得しています。"
            "DATA_URL がダウンロードページのままです。"
            "実際のデータファイルURLに差し替えてください。"
        )


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
        raise RuntimeError("CSVヘッダが見つかりません。データ形式を確認してください。")

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
        sample_headers = ", ".join(reader.fieldnames[:20])
        raise RuntimeError(
            "players が 0 件です。"
            f"CSVの列名が想定と違う可能性があります。headers={sample_headers}"
        )

    return players


def save_json(players: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    print(f"saved: {OUT_PATH}")
    print(f"players: {len(players)}")


def main() -> None:
    data, content_type = fetch_bytes(DATA_URL)
    ensure_not_html(data, content_type)
    players = parse_csv(data)
    save_json(players)


if __name__ == "__main__":
    main()