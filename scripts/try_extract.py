"""试抽工具：对指定的几篇文献运行抽取，打印结果并保存为 JSON，方便人工检查。

用法（在 biolit-kg 文件夹下）：
    python scripts/try_extract.py              # 默认 5 篇测试文献
    python scripts/try_extract.py 33029651     # 也可以指定 PMID

结果保存在 data/processed/trial_<提示词版本>.json
"""
import json
import sys
import time

from biolit.db import ROOT, get_connection
from biolit.extract.llm_client import GeminiClient
from biolit.extract.prompts import PROMPT_VERSION

# 5 篇测试文献，各覆盖一种关系类型
DEFAULT_PMIDS = [
    33029651,  # 药物相互作用导致出血（瑞典登记研究）→ interacts_with / increases_risk
    33400617,  # 白藜芦醇抑制替格瑞洛代谢        → inhibits / metabolized_by
    39147699,  # CYP3A4 诱导对替格瑞洛的影响       → induces / metabolized_by
    33887342,  # CYP2C19 基因型、氯吡格雷 vs 替格瑞洛 → 人群 + 对照药
    36837547,  # 慢性肝病患者的抗凝治疗             → contraindicated_in
]

pmids = [int(x) for x in sys.argv[1:]] or DEFAULT_PMIDS
conn = get_connection()
client = GeminiClient()
results = []

for pmid in pmids:
    paper = conn.execute("SELECT pmid, title, abstract FROM papers WHERE pmid = ?", (pmid,)).fetchone()
    if paper is None:
        print(f"PMID {pmid} 不在数据库里，跳过")
        continue

    print("=" * 70)
    print(f"PMID {pmid}：{paper['title']}")
    resp = client.extract(paper["title"], paper["abstract"])
    print(f"研究类型：{resp.result.study_type} | 用时 {resp.seconds} 秒 | "
          f"{len(resp.result.entities)} 个实体，{len(resp.result.relations)} 条关系\n")

    for r in resp.result.relations:
        extra = " | ".join(x for x in [
            f"效果：{r.effect}" if r.effect else "",
            f"对照：{r.comparator}" if r.comparator else "",
            f"人群：{r.population}" if r.population else "",
        ] if x)
        print(f"  {r.subject} --{r.relation}--> {r.object}   {extra}")

    results.append({
        "pmid": pmid,
        "title": paper["title"],
        "abstract": paper["abstract"],
        **resp.result.model_dump(),   # 把 entities 和 relations 展开放进来
    })
    time.sleep(2)   # 两次请求之间稍等，避免触发频率限制

out = ROOT / "data" / "processed" / f"trial_{PROMPT_VERSION}.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n完整结果（含原文和证据句）已保存到 {out.relative_to(ROOT)}")
