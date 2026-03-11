import json
import os
import re
from collections import defaultdict

EXTRACT_DIR = "data/extract_k"
OUT_PATH = "data/master/k_st_index.json"

RE_RESULT_LINE = re.compile(
    r"^\s*\d{2}\s+\d\s+(\d{4})\s+.+?\s+\d+\s+\d+\s+\d+\.\d+\s+\d\s+\s*([0-9]\.[0-9]{2})"
)

st_map = defaultdict(list)

for fn in sorted(os.listdir(EXTRACT_DIR)):
    if not fn.lower().startswith("k") or not fn.lower().endswith(".txt"):
        continue

    path = os.path.join(EXTRACT_DIR, fn)

    with open(path, "r", encoding="cp932", errors="ignore") as f:
        for line in f:
            m = RE_RESULT_LINE.match(line)
            if not m:
                continue

            regno = m.group(1)
            st = m.group(2)

            try:
                st_map[regno].append(float(st))
            except Exception:
                pass

out = {}
for regno, vals in st_map.items():
    if not vals:
        continue
    out[regno] = {
        "count": len(vals),
        "avg_st": round(sum(vals) / len(vals), 3),
        "st_list": vals,
    }

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("built:", len(out))