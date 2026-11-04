"""M6 问答评估 · 第 1 步：为每道题生成"候选证据"，供人工确定标准答案。

为什么要人工确定：标准答案（每题的相关文献 + 答案要点）是评估的尺子，必须由懂药学的人确认，
不能直接用系统自己的抽取结果，否则就成了"自己出题自己考"。

候选证据有两个来源，合并后交给人工判断：
1. 抽取关系：从已抽取的关系里，按 configs/qa_questions.yaml 中的 filters 找出相关的
2. 关键词：摘要里同时出现 keywords 的文献 —— 用来补上抽取漏掉的，减少对抽取结果的依赖

运行（在 biolit-kg 文件夹下，只读数据库）：
    python -m biolit.eval.qa_gold
输出：data/annotations/qa_gold_待审核.xlsx
"""
from collections import Counter, defaultdict

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from biolit.db import ACTIVE_VERSION, ROOT, get_connection

QUESTIONS = ROOT / "configs" / "qa_questions.yaml"
OUT = ROOT / "data" / "annotations" / "qa_gold_待审核.xlsx"

MAX_REL_PAPERS = 12     # 每题最多列出多少篇"抽取关系"候选
MAX_KW_PAPERS = 4       # 每题最多补充多少篇"关键词"候选
# 研究类型排序：证据等级高的排前面
STUDY_RANK = {"meta_analysis": 0, "rct": 1, "observational": 2, "clinical_pk": 3,
              "review": 4, "case_report": 5, "preclinical": 6, "other": 7, None: 8}
REL_ZH = {"increases_risk": "增加", "decreases_risk": "降低", "interacts_with": "相互作用",
          "inhibits": "抑制", "induces": "诱导", "metabolized_by": "被代谢", "transported_by": "被转运",
          "contraindicated_in": "禁用", "no_significant_difference": "无显著差异"}


def hit(value: str | None, patterns: list[str] | None) -> bool:
    if not patterns:
        return True                      # 没有限定这个字段
    v = (value or "").lower()
    return any(p.lower() in v for p in patterns)


def match(r, f: dict) -> bool:
    """判断一条关系是否满足一个 filter 块；swap 时把字段互换后再判一次。"""
    def ok(subj, obj, comp):
        return (hit(subj, f.get("subject")) and hit(obj, f.get("object"))
                and hit(comp, f.get("comparator")) and hit(r["relation"], f.get("relation"))
                and hit(r["population"], f.get("population")))
    s, o, c = r["subject_norm"], r["object_norm"], r["comparator_norm"]
    if ok(s, o, c):
        return True
    if f.get("swap") == "comparator" and c:
        return ok(c, o, s)
    if f.get("swap") == "object":
        return ok(o, s, c)
    return False


def describe(r) -> str:
    cmp = f"（对照 {r['comparator_norm']}）" if r["comparator_norm"] else ""
    eff = f"：{r['effect']}" if r["effect"] else ""
    return f"{r['subject_norm']} {REL_ZH.get(r['relation'], r['relation'])} {r['object_norm']}{cmp}{eff}"


def main():
    conn = get_connection()
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))

    rels = conn.execute(
        "SELECT r.*, e.study_type FROM relations r "
        "JOIN extractions e ON e.pmid = r.pmid AND e.prompt_version = r.prompt_version AND e.status = 'ok' "
        "WHERE r.prompt_version = ?", (ACTIVE_VERSION,)).fetchall()
    papers = {r["pmid"]: r for r in conn.execute("SELECT pmid, title, year, abstract FROM papers")}
    study = {r["pmid"]: r["study_type"] for r in rels}

    wb = Workbook()
    ws_q = wb.active
    ws_q.title = "题目"
    ws_q.append(["题号", "类别", "出题人", "范围", "问题", "候选文献数",
                 "要点草稿（自动汇总，仅供参考）", "要点（请确认或改写，每条一行）"])
    ws_e = wb.create_sheet("候选证据")
    ws_e.append(["题号", "PMID", "年份", "研究类型", "来源", "标题", "匹配的关系", "证据句（第一条）",
                 "是否相关（是/否）"])

    for q in questions:
        if q["scope"] == "out":
            ws_q.append([q["id"], q["category"], q["source"], "范围外", q["question"], 0,
                         "（范围外题：期望系统回答“检索到的文献未涉及”）", ""])
            continue

        by_paper = defaultdict(list)
        for r in rels:
            if any(match(r, f) for f in q.get("filters", [])):
                by_paper[r["pmid"]].append(r)

        # 关键词候选：摘要同时包含所有关键词，且不在上面的结果里
        kws = [k.lower() for k in q.get("keywords", [])]
        kw_papers = [pm for pm, p in papers.items()
                     if pm not in by_paper and kws and all(k in (p["abstract"] or "").lower() for k in kws)]
        kw_papers.sort(key=lambda pm: -(papers[pm]["year"] or 0))

        ranked = sorted(by_paper, key=lambda pm: (STUDY_RANK.get(study.get(pm), 8), -len(by_paper[pm])))
        chosen = ranked[:MAX_REL_PAPERS]

        # 要点草稿：把匹配到的关系按"主体-关系-客体-对照"汇总，列出支持文献最多的几条
        agg = Counter((r["subject_norm"], r["relation"], r["object_norm"], r["comparator_norm"] or "")
                      for rs in by_paper.values() for r in {(x["subject_norm"], x["relation"], x["object_norm"],
                                                              x["comparator_norm"]): x for x in rs}.values())
        draft = "\n".join(
            f"{s} {REL_ZH.get(rel, rel)} {o}" + (f"（对照 {c}）" if c else "") + f" —— {n} 篇"
            for (s, rel, o, c), n in agg.most_common(6))

        ws_q.append([q["id"], q["category"], q["source"], "范围内", q["question"],
                     len(chosen) + min(len(kw_papers), MAX_KW_PAPERS), draft, ""])

        for pm in chosen:
            rs = by_paper[pm]
            ws_e.append([q["id"], pm, papers[pm]["year"], study.get(pm), "抽取关系", papers[pm]["title"],
                         "\n".join(describe(r) for r in rs[:4]), rs[0]["evidence"], ""])
        for pm in kw_papers[:MAX_KW_PAPERS]:
            ws_e.append([q["id"], pm, papers[pm]["year"], study.get(pm), "关键词", papers[pm]["title"],
                         "", "", ""])

        print(f"{q['id']} {q['category']:<6} 抽取关系 {len(by_paper):>3} 篇（列出 {len(chosen)}）"
              f"，关键词补充 {len(kw_papers):>3} 篇（列出 {min(len(kw_papers), MAX_KW_PAPERS)}）")

    # 样式：表头加粗、自动换行、待填列标黄
    yellow = PatternFill("solid", fgColor="FFF2CC")
    for ws, widths, fill_col in [(ws_q, [6, 12, 8, 8, 50, 10, 60, 50], 8),
                                 (ws_e, [6, 10, 6, 12, 9, 60, 60, 70, 12], 9)]:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[chr(64 + i)].width = w
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            row[fill_col - 1].fill = yellow
        ws.freeze_panes = "A2"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"\n已生成 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
