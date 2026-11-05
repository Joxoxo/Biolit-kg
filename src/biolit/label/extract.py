"""说明书交叉验证 · 第 2 步：用大模型从 FDA 说明书中抽取"已知"的不良反应、相互作用和代谢途径。

和文献抽取的区别：
- 说明书很少写"相比某药降低多少"，主要写"可引起什么""和什么合用要注意""经什么酶代谢"，所以用一套更简单的格式
- 说明书常按"药物类别"写相互作用（如"P-gp 和强效 CYP3A4 联合抑制剂"），后面括号里举例具体药名。
  例子里的每个药名都单独记下，否则文献里的"克拉霉素"就对不上说明书里的"强效 CYP3A4 抑制剂"

每种药调用 2 次（不良反应类章节一次，相互作用与药代章节一次），7 种药共 14 次。
抽出的证据句用和文献相同的核验程序检查是否真的在说明书原文里 —— 同一套代码复用到新类型的文档。

运行（在 biolit-kg 文件夹下，需先运行 python -m biolit.ingest.druglabel）：
    python -m biolit.label.extract
输出：data/processed/label_facts.json
"""
import json
import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from biolit.db import ROOT
from biolit.extract.llm_client import DailyQuotaExceeded, GeminiClient
from biolit.normalize.evidence import check_evidence

LABEL_DIR = ROOT / "data" / "raw" / "labels"
OUT = ROOT / "data" / "processed" / "label_facts.json"
MIN_INTERVAL = 4.5

# 两组章节分开抽取：一次调用的输入太长，模型容易漏
GROUPS = {
    "safety": ["boxed_warning", "contraindications", "warnings_and_cautions", "adverse_reactions"],
    "interaction": ["drug_interactions", "clinical_pharmacology", "warnings_and_cautions"],
}


class Category(str, Enum):
    adverse_reaction = "adverse_reaction"      # 不良反应 / 安全性风险（如出血、脊髓血肿）
    contraindication = "contraindication"      # 禁忌（如活动性病理性出血、机械心脏瓣膜）
    interaction = "interaction"                # 与其他药物或药物类别的相互作用
    pharmacokinetics = "pharmacokinetics"      # 代谢酶 / 转运体（如 CYP3A4 底物、P-gp 底物）


class LabelFact(BaseModel):
    category: Category
    target: str = Field(description="不良反应名称 / 禁忌情形 / 相互作用的药物或药物类别 / 酶或转运体，"
                                    "用英文通用名小写，如 'bleeding'、'ketoconazole'、'strong cyp3a4 inducers'、'cyp3a4'、'p-gp'")
    examples: list[str] = Field(default_factory=list,
                                description="target 是药物类别时，说明书举例的具体药名（英文小写）；不是类别则为空")
    effect: Optional[str] = Field(default=None,
                                  description="后果或建议，英文简述，如 'increases bleeding risk'、'avoid coadministration'、"
                                              "'reduce dose by 50%'、'no dose adjustment needed'、'substrate'")
    evidence: str = Field(description="说明书原文中支持这条信息的一句话，必须逐字照抄")


class LabelExtraction(BaseModel):
    facts: list[LabelFact]


PROMPT = """你是一名药物警戒专家，从 FDA 药品说明书中提取"官方已知"的安全性信息。

规则：
1. 只提取说明书明确写出的信息，不要用自己的知识补充。
2. 不良反应：提取有临床意义的不良反应和安全性风险（如 bleeding、gastrointestinal bleeding、intracranial hemorrhage、
   spinal/epidural hematoma、thrombotic events after discontinuation）。临床试验里发生率很低、与本药关系不明的零散不良事件不提取。
3. 相互作用：每个药物或药物类别单独一条。说明书写"某类药物（例如 A、B、C）"时，target 写类别，examples 列出 A、B、C。
   说明书明确说"无需调整剂量 / 无明显相互作用"的，也要提取，effect 写 'no dose adjustment needed' 或 'no clinically relevant interaction'。
4. 药代：本药是哪些代谢酶或转运体的底物，以及本药抑制或诱导了哪些酶；target 写酶或转运体名称。
5. evidence 必须从原文逐字照抄一句话，不要改写、不要翻译。
6. 所有名称用英文小写的通用写法，不写商品名。"""


def main():
    facts = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    llm = GeminiClient()
    try:
        for path in sorted(LABEL_DIR.glob("*.json")):
            label = json.loads(path.read_text(encoding="utf-8"))
            drug = label["drug"]
            for group, sections in GROUPS.items():
                key = f"{drug}|{group}"
                if key in facts:
                    continue
                text = "\n\n".join(f"## {s}\n{label['sections'][s]}" for s in sections if s in label["sections"])
                before = llm.calls
                result = llm.generate(f"药物：{drug}\n\n{text}", PROMPT, schema=LabelExtraction)

                rows = []
                for f in result.facts:
                    status, score = check_evidence(f.evidence, text)      # 复用文献抽取的证据核验
                    rows.append({**f.model_dump(mode="json"), "drug": drug, "group": group,
                                 "evidence_status": status, "evidence_score": round(score, 3)})
                facts[key] = rows
                OUT.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")

                bad = sum(r["evidence_status"] == "unverified" for r in rows)
                print(f"{drug:<12} {group:<12} 抽出 {len(rows):>3} 条" + (f"，⚠️ {bad} 条证据句在原文中找不到" if bad else ""))
                if llm.calls > before:
                    time.sleep(MIN_INTERVAL)
    except DailyQuotaExceeded:
        print("\n今日额度已用完，已保存进度，明天重新运行即可续跑。")

    n = sum(len(v) for v in facts.values())
    print(f"\n共 {n} 条说明书信息；模型调用 {llm.calls} 次，缓存命中 {llm.cache_hits} 次")
    print(f"已保存到 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
