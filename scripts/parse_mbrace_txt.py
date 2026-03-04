# scripts/parse_mbrace_txt.py
# mbrace番組表txt → JSON
# 出力: data/mbrace_races_today.json

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

JST = timezone(timedelta(hours=9))

# 全角 → 半角変換
TRANS = str.maketrans({
    "０":"0","１":"1","２":"2","３":"3","４":"4","５":"5","６":"6","７":"7","８":"8","９":"9",
    "Ｒ":"R","Ｈ":"H","ｍ":"m","：":":","　":" "
})

def norm(s: str) -> str:
    s = (s or "").translate(TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# レースヘッダ
RE_RACE_HEAD = re.compile(
    r"^\s*([0-9]{1,2})R\s+(.+?)\s+(進入固定|進入自由)?\s*H?([0-9]{3,4})m.*?締切予定\s*([0-9]{1,2}:[0-9]{2})"
)

# 選手行
RE_BOAT_LINE = re.compile(
    r"^\s*([1-6])\s+(\d{4})\s*(\S+?)\s*([0-9]{1,2})\s*([^\d\s]{2,6})\s*([0-9]{2})\s*(A1|A2|B1|B2)\s+"
    r"([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})\s+"
    r"([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(\d{1,2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(\d{1,2})\s+([0-9]+\.[0-9]{2})\s+"
    r"(.*)$"
)

def read_text_auto(path: str):
    """
    mbrace txt は cp932 のことが多い
    """
    for enc in ["cp932", "utf-8"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.readlines()
        except:
            pass

    with open(path, "r", encoding="cp932", errors="ignore") as f:
        return f.readlines()

def parse_file(txt_path: str):

    lines_raw = read_text_auto(txt_path)
    lines = [norm(l) for l in lines_raw if l.strip()]

    venue = ""
    ymd = ""

    for l in lines[:50]:

        if "ボートレース" in l and "月" in l:
            tmp = re.sub(r"\s+", "", l.split("月")[0])
            venue = tmp.replace("ボートレース","")

        m = re.search(r"(\d{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日", l)
        if m:
            y,mo,d = m.groups()
            ymd = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            break

    races: List[Dict[str,Any]] = []
    cur: Optional[Dict[str,Any]] = None

    for l in lines:

        mh = RE_RACE_HEAD.search(l)
        if mh:

            if cur:
                races.append(cur)

            cur = {
                "rno": int(mh.group(1)),
                "name": mh.group(2),
                "shinin": (mh.group(3) or ""),
                "distance_m": int(mh.group(4)),
                "cutoff": mh.group(5),
                "boats":[]
            }
            continue

        if not cur:
            continue

        mb = RE_BOAT_LINE.match(l)
        if mb:

            (waku,regno,name,age,branch,weight,grade,
            nat_win,nat_2,loc_win,loc_2,
            motor_no,motor_2,boat_no,boat_2,rest) = mb.groups()

            cur["boats"].append({
                "waku":int(waku),
                "regno":int(regno),
                "name":name,
                "age":int(age),
                "branch":branch,
                "weight":int(weight),
                "grade":grade,
                "nat_win":float(nat_win),
                "nat_2":float(nat_2),
                "loc_win":float(loc_win),
                "loc_2":float(loc_2),
                "motor_no":int(motor_no),
                "motor_2":float(motor_2),
                "boat_no":int(boat_no),
                "boat_2":float(boat_2),
                "note":rest.strip()
            })

    if cur:
        races.append(cur)

    return {
        "source": os.path.basename(txt_path),
        "venue": venue,
        "date": ymd,
        "parsed_at": datetime.now(JST).isoformat(),
        "races": races
    }

def classify_race(race: Dict[str,Any]):

    tags=[]

    nm=race.get("name","")

    if "女子" in nm or "レディース" in nm:
        tags.append("女子戦")

    boats=race.get("boats",[])

    if boats:

        b2=sum(1 for b in boats if b["grade"]=="B2")
        low=sum(1 for b in boats if b["nat_win"]<=3.0)

        if b2>=2:
            tags.append("新人多め")

        if low>=4:
            tags.append("荒れ注意")

        one=next((b for b in boats if b["waku"]==1),None)

        if one and one["nat_win"]>=6:
            weak=sum(1 for b in boats if b["waku"]!=1 and b["nat_win"]<=4)
            if weak>=4:
                tags.append("鉄板寄り")

    return tags

def main():

    txt_path=os.path.join("data","extract","b260303.txt")

    data=parse_file(txt_path)

    for r in data["races"]:
        r["tags"]=classify_race(r)

    out_path=os.path.join("data","mbrace_races_today.json")

    os.makedirs(os.path.dirname(out_path),exist_ok=True)

    with open(out_path,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)

    print("venue:",data["venue"])
    print("date:",data["date"])
    print("races:",len(data["races"]))

if __name__=="__main__":
    main()