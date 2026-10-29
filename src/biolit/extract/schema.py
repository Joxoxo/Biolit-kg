"""M2 抽取格式：用 Pydantic 规定大模型必须返回什么结构。

为什么用 Pydantic：
- 把"实体有哪些字段、关系类型只能是哪几种"写成代码，一目了然
- 模型返回的结果会被自动校验：类型写错、字段缺失都会报错，而不是悄悄存进数据库
- 可以直接转成 JSON Schema 交给 Gemini，让模型严格按格式输出

设计原则：类型粗一点，名称细一点。
类型只分 6 大类，具体名称保留原文（如 "intracranial hemorrhage"），以后用 SQL 再细分。
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------- 允许的类型（Literal = 只能取这几个值之一）----------

EntityType = Literal[
    "drug",            # 药物：apixaban, amiodarone
    "adverse_event",   # 不良事件（安全性终点）：major bleeding, GI bleeding
    "outcome",         # 临床结局（有效性终点）：ischemic stroke, systemic embolism, mortality
    "disease",         # 疾病 / 适应症：atrial fibrillation, CKD
    "enzyme",          # 代谢酶 / 转运体：CYP3A4, P-gp
    "population",      # 人群：elderly, dialysis patients
]

RelationType = Literal[
    "increases_risk",      # 增加风险：warfarin → intracranial hemorrhage
    "decreases_risk",      # 降低风险：apixaban → major bleeding
    "interacts_with",      # 药物相互作用：warfarin ↔ amiodarone
    "inhibits",            # 抑制：ketoconazole → CYP3A4
    "induces",             # 诱导：rifampin → CYP3A4
    "metabolized_by",      # 被代谢：rivaroxaban → CYP3A4
    "contraindicated_in",  # 禁用：dabigatran → severe renal impairment
]

StudyType = Literal[
    "rct",            # 随机对照试验
    "meta_analysis",  # 系统综述 / Meta 分析
    "observational",  # 观察性研究：队列、病例对照、登记数据库
    "clinical_pk",    # 人体药代 / 药效学研究（含健康志愿者）
    "case_report",    # 病例报告 / 病例系列
    "review",         # 叙述性综述、指南、专家共识
    "preclinical",    # 动物实验或体外实验
    "other",
]


# ---------- 实体和关系的结构 ----------

class Entity(BaseModel):
    name: str = Field(description="实体名称，照抄原文写法")
    type: EntityType


class Relation(BaseModel):
    subject: str = Field(description="关系的主体，通常是药物，照抄原文")
    relation: RelationType
    object: str = Field(description="关系的客体，照抄原文")
    comparator: Optional[str] = Field(
        default=None,
        description="对照药。如 'apixaban 相比 warfarin 出血更少'，对照药为 warfarin；没有对照则为 null",
    )
    effect: Optional[str] = Field(
        default=None,
        description="关系的具体效果，尤其是相互作用的后果，如 'increased ticagrelor AUC'、"
                    "'increased risk of severe bleeding'；没有具体描述则为 null",
    )
    population: Optional[str] = Field(
        default=None,
        description="适用人群，如 'patients with CKD'；没有特别说明则为 null",
    )
    evidence: str = Field(description="原文中支持这条关系的句子，必须逐字照抄，不能改写")


class ExtractionResult(BaseModel):
    """一篇摘要的完整抽取结果 = 研究类型 + 实体列表 + 关系列表。"""
    study_type: StudyType = Field(description="这篇文献的研究类型，用于判断证据强度")
    entities: list[Entity]
    relations: list[Relation]


if __name__ == "__main__":
    # 自测：构造一条合法数据，再故意构造一条非法数据，看 Pydantic 能否拦下
    ok = Relation(
        subject="apixaban", relation="decreases_risk", object="major bleeding",
        comparator="warfarin", population="patients with advanced CKD",
        evidence="Apixaban was associated with a lower risk of major bleeding compared with warfarin.",
    )
    print("合法数据：", ok.model_dump(), "\n")

    try:
        Relation(subject="apixaban", relation="cures", object="AF", evidence="...")
    except Exception as e:
        print("非法数据被拦下：relation='cures' 不在允许的类型里")
        print(str(e).splitlines()[0])
