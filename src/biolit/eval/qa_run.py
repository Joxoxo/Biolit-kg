"""M6 问答评估 · 第 2 步：让三个系统回答题库里的 30 道题，保存回答和检索结果。

三个系统（消融实验）：
    A llm_only：纯大模型，不检索
    B vector  ：只用向量检索文献（普通 RAG）
    C hybrid  ：向量 + 实体匹配 + 知识图谱（正式版 GraphRAG）

额度：30 题 ×（A 1 次 + B 2 次 + C 2 次）= 150 次，其中 B 和 C 的"问题解析"完全相同，
第二次会命中缓存，所以实际约 120 次。已经回答过的题会跳过，中断后重新运行即可续跑。

运行（在 biolit-kg 文件夹下）：
    python -m biolit.eval.qa_run              # 跑全部
    python -m biolit.eval.qa_run --limit 3    # 先用前 3 题试跑
输出：data/annotations/qa_runs.json
"""
import argparse
import json
import time

import yaml

from biolit.db import ROOT
from biolit.extract.llm_client import DailyQuotaExceeded
from biolit.rag.answer import MODES, QA

QUESTIONS = ROOT / "configs" / "qa_questions.yaml"
OUT = ROOT / "data" / "annotations" / "qa_runs.json"
MIN_INTERVAL = 4.5      # 两次真实调用之间至少间隔几秒（免费版每分钟 15 次）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 题")
    args = ap.parse_args()

    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))[:args.limit]
    runs = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    qa = QA()

    try:
        for q in questions:
            for mode in MODES:
                key = f"{q['id']}|{mode}"
                if key in runs:
                    continue
                before = qa.llm.calls
                start = time.time()
                ans = qa.ask(q["question"], mode=mode)
                res = ans.retrieval
                runs[key] = {
                    "id": q["id"], "mode": mode, "question": q["question"],
                    "answer": ans.text,
                    "cited": ans.cited,
                    "invalid_citations": ans.invalid_citations,
                    "entities": res.entities_norm,
                    "retrieved": [{"pmid": p.pmid, "score": round(p.score, 4),
                                   "vector": round(p.vector_score, 4), "matched": p.matched}
                                  for p in res.papers],
                    "n_graph_facts": len(res.graph_facts),
                    "seconds": round(time.time() - start, 1),
                }
                OUT.write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"{q['id']} {mode:<8} 检索 {[p.pmid for p in res.papers]} 引用 {len(ans.cited)} 篇"
                      + (f" ⚠️无效引用 {ans.invalid_citations}" if ans.invalid_citations else ""))
                # 只有真正调用了模型才需要等待；命中缓存时直接继续
                if qa.llm.calls > before:
                    time.sleep(MIN_INTERVAL)
    except DailyQuotaExceeded:
        print("\n今日额度已用完，已保存进度。明天重新运行同一条命令即可续跑。")

    print(f"\n共 {len(runs)} 条回答；本次模型调用 {qa.llm.calls} 次，缓存命中 {qa.llm.cache_hits} 次")
    print(f"已保存到 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
