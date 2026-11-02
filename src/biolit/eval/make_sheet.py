"""M6 第 1 步：抽样并生成人工标注表（Excel）。

抽样方法（分层随机抽样，固定随机种子，结果可复现）：
- 32 篇"有抽取结果"的文献：按研究类型分层，每类至少 2 篇，其余按比例分配
- 8 篇"没抽出任何关系"的文献：检查模型是不是漏抽了

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.eval.make_sheet
输出：data/annotations/annotation_<提示词版本>.xlsx
"""
import random
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from biolit.db import ROOT, get_connection
from biolit.extract.prompts import PROMPT_VERSION

SEED = 42
N_WITH_REL, N_WITHOUT_REL, MIN_PER_TYPE = 32, 8, 2
OUT = ROOT / "data" / "annotations" / f"annotation_{PROMPT_VERSION}.xlsx"

REL_ZH = {"increases_risk": "增加风险", "decreases_risk": "降低风险", "interacts_with": "相互作用",
          "inhibits": "抑制", "induces": "诱导", "metabolized_by": "被代谢", "contraindicated_in": "禁用"}
JUDGEMENTS = ["正确", "部分正确", "错误", "漏抽"]

GUIDE = [
    ("标注说明", ""),
    ("目标", "判断模型抽取的每条关系是否正确，并补充模型漏掉的关系。"),
    ("原则", "判定依据只看标题 + 摘要，不看全文；全文中的额外信息可写在备注，但不参与判定。"),
    ("步骤 1", "先读摘要，自己心里有个判断，再看模型抽了什么（避免被模型的答案带偏）。"),
    ("步骤 2", "在 K 列「判定」下拉选择："),
    ("  正确", "主体、关系类型、客体都对，且原文明确支持（对照药、人群等次要字段允许小瑕疵）。"),
    ("  部分正确", "主要关系对，但对照药 / 效果 / 人群有明显错误，或主客体写得不准确。"),
    ("  错误", "关系方向错、类型错、原文没有这个结论，或结论无统计学意义却被抽了出来。"),
    ("步骤 3", "模型漏掉的关系，填在每篇文献下方的空行里（D–I 列），K 列选「漏抽」。"),
    ("步骤 4", "有疑问的写在 L 列「备注」，比如应该怎么写才对。"),
    ("特殊情况", "复合终点被拆成单个组分 → 错误；结论措辞超出结果数据 → 以数据为准。完整约定见 data/annotations/标注规范.md"),
    ("提示", "不必一次做完，保存后随时可以继续；评分脚本只统计已经填了判定的文献。"),
]


def sample_pmids(conn) -> list[int]:
    rng = random.Random(SEED)
    rows = conn.execute(
        "SELECT e.pmid, e.study_type, (SELECT COUNT(*) FROM relations r WHERE r.pmid = e.pmid "
        "AND r.prompt_version = e.prompt_version AND r.model = e.model) AS n "
        "FROM extractions e WHERE e.status = 'ok' AND e.prompt_version = ?", (PROMPT_VERSION,)).fetchall()

    with_rel = defaultdict(list)
    without_rel = []
    for r in rows:
        (with_rel[r["study_type"]] if r["n"] > 0 else without_rel).append(r["pmid"])

    # 分层：每类先保底 MIN_PER_TYPE 篇，剩余名额按各类文献数量比例分配
    picked = []
    for t, pmids in with_rel.items():
        picked += rng.sample(sorted(pmids), min(MIN_PER_TYPE, len(pmids)))
    rest = [p for t in with_rel for p in with_rel[t] if p not in picked]
    picked += rng.sample(sorted(rest), N_WITH_REL - len(picked))
    picked += rng.sample(sorted(without_rel), N_WITHOUT_REL)
    return picked


def main():
    conn = get_connection()
    pmids = sample_pmids(conn)

    wb = Workbook()
    guide = wb.active
    guide.title = "说明"
    for i, (a, b) in enumerate(GUIDE, 1):
        guide.cell(i, 1, a).font = Font(bold=(i == 1 or not a.startswith(" ")))
        guide.cell(i, 2, b)
    guide.column_dimensions["A"].width = 14
    guide.column_dimensions["B"].width = 100

    ws = wb.create_sheet("标注")
    headers = ["序号", "PMID", "研究类型", "主体", "关系", "客体", "对照药", "效果", "人群",
               "证据句", "判定", "备注", "rel_id"]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4A6FA5")
    widths = [6, 11, 13, 22, 10, 26, 16, 26, 22, 60, 11, 30, 8]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "A2"

    dv = DataValidation(type="list", formula1=f'"{",".join(JUDGEMENTS)}"', allow_blank=True)
    ws.add_data_validation(dv)
    paper_fill = PatternFill("solid", fgColor="E8EEF6")
    wrap = Alignment(wrap_text=True, vertical="top")

    n_rel = 0
    for idx, pmid in enumerate(pmids, 1):
        p = conn.execute(
            "SELECT p.title, p.abstract, e.study_type FROM papers p JOIN extractions e ON e.pmid = p.pmid "
            "AND e.status = 'ok' AND e.prompt_version = ? WHERE p.pmid = ?", (PROMPT_VERSION, pmid)).fetchone()

        # 文献标题行
        ws.append([idx, pmid, p["study_type"], p["title"]])
        r = ws.max_row
        ws.cell(r, 2).hyperlink = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=12)
        for c in ws[r]:
            c.fill = paper_fill
            c.font = Font(bold=True)
            c.alignment = wrap
        ws.row_dimensions[r].height = 32

        # 摘要行（合并单元格的行高 Excel 不会自动调整，按字数估算）
        ws.append(["", "", "摘要", p["abstract"]])
        r = ws.max_row
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=12)
        ws.cell(r, 4).alignment = wrap
        ws.row_dimensions[r].height = min(409, 15 * (len(p["abstract"]) // 170 + 2))

        # 模型抽取的关系
        rels = conn.execute(
            "SELECT id, subject, relation, object, comparator, effect, population, evidence FROM relations "
            "WHERE pmid = ? AND prompt_version = ? ORDER BY id", (pmid, PROMPT_VERSION)).fetchall()
        for rel in rels:
            ws.append(["", pmid, "", rel["subject"], REL_ZH.get(rel["relation"], rel["relation"]), rel["object"],
                       rel["comparator"], rel["effect"], rel["population"], rel["evidence"], "", "", rel["id"]])
            r = ws.max_row
            for c in ws[r]:
                c.alignment = wrap
            dv.add(ws.cell(r, 11))
            n_rel += 1

        # 漏抽补充行
        for _ in range(2):
            ws.append(["", pmid, "（漏抽）"])
            r = ws.max_row
            ws.cell(r, 3).font = Font(color="999999")
            dv.add(ws.cell(r, 11))

    rel_dv = DataValidation(type="list", formula1=f'"{",".join(REL_ZH.values())}"', allow_blank=True)
    ws.add_data_validation(rel_dv)
    rel_dv.add(f"E2:E{ws.max_row}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"抽样 {len(pmids)} 篇（有关系 {N_WITH_REL} 篇 + 无关系 {N_WITHOUT_REL} 篇），共 {n_rel} 条待判定的关系")
    print(f"标注表：{OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
