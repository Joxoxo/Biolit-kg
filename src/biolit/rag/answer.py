"""M5 第 3 步：生成回答 —— 把检索到的证据交给大模型，生成带引用的中文回答。

防幻觉的三道关：
1. 提示词规定：只能根据给定材料回答，材料里没有就明确说"现有文献未涉及"
2. 每个结论后必须标注引用 [PMID:xxxxx]
3. 生成后用代码检查：引用的 PMID 必须在本次检索结果里，否则标记为"无效引用"

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.rag.answer "你的问题"
    python -m biolit.rag.answer          # 不带问题时，运行内置的示例问题
"""
import re
import sys
from dataclasses import dataclass

from biolit.rag.retrieve import RetrievalResult, Retriever

REL_ZH = {"increases_risk": "增加风险", "decreases_risk": "降低风险", "interacts_with": "相互作用",
          "inhibits": "抑制", "induces": "诱导", "metabolized_by": "被代谢", "contraindicated_in": "禁用"}

ANSWER_PROMPT = """你是一名临床药学信息助手，回答关于口服抗栓药物安全性的问题。

你会收到两类材料：
A. 知识图谱统计：从近千篇文献中自动抽取、汇总的关系及支持文献数（可能有抽取误差，仅作参考）
B. 文献摘要：与问题最相关的几篇原文摘要，每篇带有 PMID、年份和研究类型

回答要求：
1. 只能使用材料中的信息，不得使用你自己的知识补充。材料不足以回答时，直接说"现有检索到的文献未涉及这一点"。
2. 每个具体结论后标注来源，格式为 [PMID:12345678]；引用知识图谱统计时写 [图谱]。
3. 说明证据强度：优先引用 Meta 分析和 RCT 的结论，并指出研究类型；不同研究结论不一致时要明确指出。
4. 结构：先用 1–2 句话给出结论，再分点列出证据，最后用一句话说明局限性。
5. 用中文回答，药名首次出现时附英文名。
6. 结尾固定加一句："以上内容基于文献自动检索，不构成用药建议。"
"""


@dataclass
class Answer:
    question: str
    text: str
    cited: list[int]
    invalid_citations: list[int]
    retrieval: RetrievalResult


def build_context(res: RetrievalResult) -> str:
    """把检索结果整理成交给大模型的材料。"""
    parts = ["## A. 知识图谱统计"]
    if res.graph_facts:
        for f in res.graph_facts:
            cmp = f"（对照：{f['comparator']}）" if f["comparator"] else ""
            types = "、".join(f"{k} {v}" for k, v in f["study_types"].items())
            parts.append(f"- {f['subject']} {REL_ZH.get(f['relation'], f['relation'])} {f['object']}{cmp}："
                         f"{f['n_papers']} 篇文献支持（{types}）")
    else:
        parts.append("（无相关统计）")

    parts.append("\n## B. 文献摘要")
    for p in res.papers:
        parts.append(f"\n[PMID:{p.pmid}] {p.year} · 研究类型：{p.study_type} · {p.journal}\n"
                     f"标题：{p.title}\n摘要：{p.abstract}")
    return "\n".join(parts)


class QA:
    def __init__(self):
        self.retriever = Retriever()
        self.llm = self.retriever.llm      # 复用同一个模型客户端

    def ask(self, question: str, k: int = 5) -> Answer:
        res = self.retriever.retrieve(question, k=k)
        prompt = f"问题：{question}\n\n{build_context(res)}"
        text = self.llm.generate(prompt, ANSWER_PROMPT)

        # 第三道关：检查引用是否都来自本次检索结果
        cited = sorted({int(x) for x in re.findall(r"PMID:\s*(\d+)", text)})
        allowed = {p.pmid for p in res.papers}
        invalid = [c for c in cited if c not in allowed]
        return Answer(question, text, cited, invalid, res)


def show(ans: Answer):
    print("=" * 70)
    print(f"问题：{ans.question}")
    print(f"识别实体：{ans.retrieval.entities_norm} | 检索文献：{[p.pmid for p in ans.retrieval.papers]}")
    print("-" * 70)
    print(ans.text)
    print("-" * 70)
    print(f"引用了 {len(ans.cited)} 篇：{ans.cited}")
    if ans.invalid_citations:
        print(f"⚠️ 无效引用（不在检索结果中，可能是模型编造）：{ans.invalid_citations}")


if __name__ == "__main__":
    qa = QA()
    questions = sys.argv[1:] or [
        "阿哌沙班和华法林相比，大出血风险怎么样？",
        "哪些药物会通过 CYP3A4 影响替格瑞洛的血药浓度？",
        "达比加群会增加消化道出血吗？",
    ]
    for q in questions:
        show(qa.ask(q))
