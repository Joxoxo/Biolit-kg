"""M3 说明书交叉验证 · 第 1 步：从 openFDA 下载 7 种药的说明书。

openFDA 是美国 FDA 的免费公开接口，不需要注册；不带 Key 时每天限 1000 次请求，这里只用 7 次。
接口文档：https://open.fda.gov/apis/drug/label/

同一种药会有很多份说明书（原研 + 各家仿制药），挑选规则：
1. 只要处方药（HUMAN PRESCRIPTION DRUG）
2. 优先选商品名等于原研品牌的（配置在 configs/druglabel.yaml）
3. 同样条件下选生效日期最新的

运行（在 biolit-kg 文件夹下）：
    python -m biolit.ingest.druglabel
输出：data/raw/labels/<药名>.json（每种药一个文件）
"""
import json
import time

import requests
import yaml

from biolit.db import ROOT

API = "https://api.fda.gov/drug/label.json"
CONFIG = ROOT / "configs" / "druglabel.yaml"
OUT_DIR = ROOT / "data" / "raw" / "labels"


def fetch_labels(generic: str) -> list[dict]:
    """按通用名搜索，返回所有匹配的说明书（最多 100 份）。"""
    params = {"search": f'openfda.generic_name:"{generic}"', "limit": 100}
    for attempt in range(3):
        r = requests.get(API, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()["results"]
        if r.status_code == 404:          # openFDA 用 404 表示"没有搜到"
            return []
        time.sleep(3 * (attempt + 1))
    r.raise_for_status()


def pick(labels: list[dict], generic: str, brand: str) -> dict | None:
    def info(lab, key):
        return [x.lower() for x in lab.get("openfda", {}).get(key, [])]

    candidates = [lab for lab in labels
                  if "human prescription drug" in info(lab, "product_type")
                  # 排除复方制剂：通用名必须正好是这个药（例如排除 "aspirin and dipyridamole" 这类）
                  and any(g.strip() == generic or g.startswith(generic + " ") for g in info(lab, "generic_name"))]
    if not candidates:
        return None
    if brand:
        branded = [lab for lab in candidates if brand.lower() in info(lab, "brand_name")]
        candidates = branded or candidates
    return max(candidates, key=lambda lab: lab.get("effective_time", ""))


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for generic, brand in cfg["drugs"].items():
        labels = fetch_labels(generic)
        lab = pick(labels, generic, brand or "")
        if lab is None:
            print(f"✗ {generic}：没有找到合适的说明书（共搜到 {len(labels)} 份）")
            continue

        ofda = lab.get("openfda", {})
        record = {
            "drug": generic,
            "brand": ofda.get("brand_name", []),
            "manufacturer": ofda.get("manufacturer_name", []),
            "effective_time": lab.get("effective_time"),
            "set_id": lab.get("set_id"),     # 说明书的固定编号，可在 DailyMed 上查到原文
            # openFDA 里每个章节是一个字符串列表，这里拼成一段文字
            "sections": {s: "\n".join(lab[s]) for s in cfg["sections"] if s in lab},
        }
        path = OUT_DIR / f"{generic}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")

        sizes = "、".join(f"{k} {len(v):,} 字" for k, v in record["sections"].items())
        print(f"✓ {generic}：{', '.join(record['brand'])}（{record['effective_time']}，"
              f"从 {len(labels)} 份中选出）\n    {sizes}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
