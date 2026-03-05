# scripts/build_site_json.py
# mbrace_races_today.json からサイト用 venues.json / races index 等を生成
# ※ここでは venues.json を「mbrace一本」に固定する

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

JST = timezone(timedelta(hours=9))

# 公式順 + jcd対応
VENUES = [
  {"jcd":"01","name":"桐生"}, {"jcd":"02","name":"戸田"}, {"jcd":"03","name":"江戸川"}, {"jcd":"04","name":"平和島"},
  {"jcd":"05","name":"多摩川"}, {"jcd":"06","name":"浜名湖"}, {"jcd":"07","name":"蒲郡"}, {"jcd":"08","name":"常滑"},
  {"jcd":"09","name":"津"}, {"jcd":"10","name":"三国"}, {"jcd":"11","name":"びわこ"}, {"jcd":"12","name":"住之江"},
  {"jcd":"13","name":"尼崎"}, {"jcd":"14","name":"鳴門"}, {"jcd":"15","name":"丸亀"}, {"jcd":"16","name":"児島"},
  {"jcd":"17","name":"宮島"}, {"jcd":"18","name":"徳山"}, {"jcd":"19","name":"下関"}, {"jcd":"20","name":"若松"},
  {"jcd":"21","name":"芦屋"}, {"jcd":"22","name":"福岡"}, {"jcd":"23","name":"唐津"}, {"jcd":"24","name":"大村"},
]
NAME_TO_JCD = {v["name"]: v["jcd"] for v in VENUES}

def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _hm_to_minutes(hm: str) -> Optional[int]:
    if not hm:
        return None
    s = str(hm).strip()
    if len(s) >= 5:
        s = s[:5]
    if ":" not in s:
        return None
    try:
        hh, mm = s.split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        return None

def _now_minutes_jst() -> int:
    n = datetime.now(JST)
    return n.hour * 60 + n.minute

def _pick_next_race(races: List[Dict[str, Any]], now_min: int) -> Tuple[Optional[int], Optional[str]]:
    """
    races: [{rno, cutoff("11:03"), ...}]
    return: (next_race, "HH:MM")
    """
    # cutoffが取れるものだけ
    items: List[Tuple[int,int,str]] = []
    for r in races or []:
        rno = r.get("rno")
        cutoff = r.get("cutoff")
        tmin = _hm_to_minutes(cutoff)
        if isinstance(rno, int) and tmin is not None:
            items.append((tmin, rno, cutoff[:5]))

    if not items:
        return (None, None)

    items.sort(key=lambda x: x[0])

    # 未来の最小
    for tmin, rno, hm in items:
        if tmin > now_min:
            return (rno, hm)

    # 全部過ぎてたら最終レース（「終了」にしても良いが、表示崩れ防止で最後を返す）
    tmin, rno, hm = items[-1]
    return (rno, hm)

def main() -> None:
    src_path = os.path.join("data", "mbrace_races_today.json")
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"missing: {src_path}")

    src = _read_json(src_path)
    venues = src.get("venues") or []
    now_min = _now_minutes_jst()

    out: List[Dict[str, Any]] = []

    for v in venues:
        name = str(v.get("venue") or "").strip()
        races = v.get("races") or []
        if not name or not isinstance(races, list) or not races:
            continue

        jcd = NAME_TO_JCD.get(name)
        if not jcd:
            # 会場名が想定外ならスキップ（ログで気づけるようにしてもOK）
            continue

        next_race, hm = _pick_next_race(races, now_min)
        if next_race is None or hm is None:
            continue

        out.append({
            "name": name,
            "jcd": jcd,
            "next_race": int(next_race),
            "next_display": f"{int(next_race)}R {hm}",
        })

    # 公式順で並べる（表示の安定）
    order = {v["jcd"]: i for i, v in enumerate(VENUES)}
    out.sort(key=lambda x: order.get(x["jcd"], 999))

    dst_path = os.path.join("data", "site", "venues.json")
    _write_json(dst_path, out)

    print("built:", dst_path, "count=", len(out))

if __name__ == "__main__":
    main()