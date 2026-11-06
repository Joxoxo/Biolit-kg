"""部署前预热缓存：把网页上的示例问题先问一遍、示例摘要先抽取一遍，存进 llm_cache.db。

部署后，访客点示例问题会直接命中缓存：秒回、不消耗额度；
即使当天的演示额度用完（只读缓存模式），示例问题也照样能回答。
问答评估的 30 道题在跑评估时已经存进缓存了，也能直接命中。

运行（在 biolit-kg 文件夹下）：
    python scripts/warm_cache.py
注意：这里的问题要和 app/src/pages/QaPage.tsx 里的 EXAMPLES 保持一致（一个字都不能差，否则缓存对不上）。
"""
from biolit.api.main import EXAMPLE_PMID
from biolit.db import get_connection
from biolit.rag.answer import QA

EXAMPLES = [
    "阿哌沙班和华法林相比，大出血风险怎么样？",
    "哪些药物会通过 CYP3A4 影响替格瑞洛的血药浓度？",
    "达比加群会增加消化道出血吗？",
]

if __name__ == "__main__":
    qa = QA()
    for q in EXAMPLES:
        ans = qa.ask(q)
        print(f"✓ {q}（引用 {len(ans.cited)} 篇）")

    # 在线抽取的示例摘要（"填入示例摘要"按钮）
    row = get_connection().execute("SELECT title, abstract FROM papers WHERE pmid = ?", (EXAMPLE_PMID,)).fetchone()
    resp = qa.llm.extract(row["title"], row["abstract"])
    print(f"✓ 示例摘要 PMID {EXAMPLE_PMID}（抽出 {len(resp.result.relations)} 条关系）")
    print(f"\n模型调用 {qa.llm.calls} 次，缓存命中 {qa.llm.cache_hits} 次")
