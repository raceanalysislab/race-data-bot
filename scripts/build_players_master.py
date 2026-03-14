import json
import pathlib

SRC = pathlib.Path("data/master/raw/fan2510.txt")
K_RESULTS = pathlib.Path("data/k_results_parsed.json")
OUT = pathlib.Path("data/master/players_master.json")

players = {}

def clean_name(s: str) -> str:
    return s.replace("　", "").replace(" ", "").strip()

# ここに誤判定した名前だけ後から追加していく
NAME_SPLIT_OVERRIDES = {
    "宮之原輝紀": ("宮之原", "輝紀"),
    "大橋純一郎": ("大橋", "純一郎"),
    "渡邉真奈美": ("渡邉", "真奈美"),
    "木下虎之輔": ("木下", "虎之輔"),
    "宇佐見淳": ("宇佐見", "淳"),
    "青木幸太郎": ("青木", "幸太郎"),
    "中嶋健一郎": ("中嶋", "健一郎"),
    "岩崎芳美": ("岩崎", "芳美"),
    "笠野友紀恵": ("笠野", "友紀恵"),
    "石井裕美": ("石井", "裕美"),
    "西澤日花里": ("西澤", "日花里"),
    "佐々木裕美": ("佐々木", "裕美"),
    "寺田夢生": ("寺田", "夢生"),
    "櫻葉新心": ("櫻葉", "新心"),
    "川崎智稔": ("川崎", "智稔"),
    "間庭菜摘": ("間庭", "菜摘"),
    "中村駿平": ("中村", "駿平"),
    "畑竜生": ("畑", "竜生"),
}

# 先頭一致で使う名字ヒント
LASTNAME_HINTS = sorted({
    "宮之原", "宇佐見", "佐々木", "渡邉", "中嶋", "櫻葉",
    "西澤", "笠野", "岩崎", "川崎", "間庭", "中村",
    "鳥飼", "奥村", "梶山", "深川", "里岡", "岩永",
    "長尾", "柏野", "荻野", "根岸", "大町", "大井",
    "上村", "落合", "眞田", "仲口", "木村", "土屋",
    "山崎", "小川", "高橋", "大橋", "木下", "青木",
    "中島", "吉村", "水摩", "石井", "寺田", "富山",
    "西島", "高田", "山口", "山本", "田中", "中野",
    "中田", "中川", "岡田", "岡本", "松本", "松井",
    "近藤", "加藤", "佐藤", "伊藤", "斎藤", "後藤",
    "前田", "武田", "池田", "村田", "森田", "岡村",
    "今村", "平田", "柴田", "藤田", "藤原", "福田",
    "浜田", "原田", "岩田", "古賀", "古川", "安田",
    "野田", "本田", "荒井", "三浦", "丸岡", "丸野",
    "西村", "東本", "東口", "南野", "北川", "北村",
    "白井", "黒井", "堀本", "坂本", "川北", "川上",
    "川下", "河合", "河野", "上田", "下田", "金子",
    "森野", "若林", "竹井", "竹田", "森", "畑"
}, key=len, reverse=True)

def split_name(name: str):
    name = clean_name(name)

    if not name:
        return "", ""

    if name in NAME_SPLIT_OVERRIDES:
        return NAME_SPLIT_OVERRIDES[name]

    for last in LASTNAME_HINTS:
        if name.startswith(last) and len(name) > len(last):
            return last, name[len(last):]

    # ヒントに無い場合の素直なフォールバック
    n = len(name)

    if n == 1:
        return name, ""
    if n == 2:
        return name[:1], name[1:]
    if n == 3:
        return name[:1], name[1:]
    if n == 4:
        return name[:2], name[2:]
    if n == 5:
        return name[:2], name[2:]
    if n == 6:
        return name[:3], name[3:]

    return name[:-2], name[-2:]

# fanマスター（名前）
with open(SRC, "r", encoding="cp932", errors="ignore") as f:
    for line in f:
        if len(line) < 40:
            continue

        reg = line[0:4].strip()
        if not reg.isdigit():
            continue

        name = clean_name(line[4:12])
        sei, mei = split_name(name)

        players[reg] = {
            "reg": reg,
            "name": name,
            "sei": sei,
            "mei": mei,
            "starts": 0,
            "wins": 0,
            "top2": 0,
            "top3": 0,
            "courses": {str(i): {"starts": 0, "wins": 0} for i in range(1, 7)}
        }

# k結果から成績作る
if K_RESULTS.exists():
    with open(K_RESULTS, "r", encoding="utf-8") as f:
        data = json.load(f)

    for venue in data["venues"]:
        for race in venue["races"]:
            for r in race["results"]:
                reg = str(r["reg"])
                if reg not in players:
                    continue

                finish = r["finish"]
                course = str(r["course"])

                p = players[reg]
                p["starts"] += 1

                if isinstance(finish, int):
                    if finish == 1:
                        p["wins"] += 1

                    if finish <= 2:
                        p["top2"] += 1

                    if finish <= 3:
                        p["top3"] += 1

                    if course in p["courses"]:
                        p["courses"][course]["starts"] += 1

                        if finish == 1:
                            p["courses"][course]["wins"] += 1

# 最終率計算
for reg, p in players.items():
    starts = p["starts"]

    if starts > 0:
        p["win_rate"] = round(p["wins"] / starts * 100, 2)
        p["top2_rate"] = round(p["top2"] / starts * 100, 2)
        p["top3_rate"] = round(p["top3"] / starts * 100, 2)
    else:
        p["win_rate"] = 0
        p["top2_rate"] = 0
        p["top3_rate"] = 0

OUT.parent.mkdir(parents=True, exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(players, f, ensure_ascii=False, indent=2)

print("players_master built:", len(players))