"""M6 问答评估 · 第 4 步：汇总指标，生成报告。

三个子命令（在 biolit-kg 文件夹下运行）：
    python -m biolit.eval.qa_score pool     # 列出系统检索到、但还没人工判过相关性的文献 → 补判表
    python -m biolit.eval.qa_score review   # 抽 20 份打分结果给人工复核 → 复核表
    python -m biolit.eval.qa_score          # 汇总所有指标 → data/annotations/eval_qa.md

指标：
- 检索 Precision@5：前 5 篇里人工判为"相关"的比例（只有 B、C 有检索）
- 要点覆盖率：（覆盖 + 0.5 × 部分覆盖）/ 要点数
- 引用支持率：被摘要支持的引用 / 全部引用（部分支持按 0.5）
- 无效引用：引用了不在检索结果里的 PMID（代码检查，不靠模型）
- 矛盾数：与参考要点明确相反的结论
- 范围外题：拒答率（明确说文献未涉及）、编造率（仍给出实质结论）
"""
import json
import random
import sys
from collections import defaultdict

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from biolit.db import ROOT, get_connection
from biolit.rag.answer import MODES

ANN = ROOT / "data" / "annotations"
QUESTIONS = ROOT / "configs" / "qa_questions.yaml"
GOLD = ANN / "qa_gold_已审核.xlsx"
POOL = ANN / "qa_pool_待补判.xlsx"          # pool 子命令生成，你填好后另存为 qa_pool_已补判.xlsx
POOL_DONE = ANN / "qa_pool_已补判.xlsx"
REVIEW = ANN / "qa_review_待复核.xlsx"
RUNS = ANN / "qa_runs.json"
JUDGE = ANN / "qa_judge.json"
REPORT = ANN / "eval_qa.md"

NAME = {"llm_only": "A 纯大模型", "vector": "B 向量 RAG", "hybrid": "C GraphRAG"}
COV = {"覆盖": 1.0, "部分覆盖": 0.5, "未覆盖": 0.0}
SUP = {"支持": 1.0, "部分支持": 0.5, "不支持": 0.0}


def load_relevance() -> dict[tuple[str, int], bool]:
    """人工相关性判断：(题号, PMID) → 是否相关。合并初审表和补判表。"""
    rel = {}
    for path, sheet in [(GOLD, "候选证据"), (POOL_DONE, "补判")]:
        if not path.exists():
            continue
        for row in load_workbook(path, read_only=True)[sheet].iter_rows(min_row=2, values_only=True):
            qid, pmid, judge = row[0], row[1], row[-1]
            if qid and pmid and judge in ("是", "否"):
                rel[(qid, int(pmid))] = judge == "是"
    return rel


def style(ws, widths, fill_cols):
    yellow = PatternFill("solid", fgColor="FFF2CC")
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = w
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for col in fill_cols:
            row[col - 1].fill = yellow
    ws.freeze_panes = "A2"


def pool():
    runs = json.loads(RUNS.read_text(encoding="utf-8"))
    rel = load_relevance()
    conn = get_connection()
    todo = sorted({(r["id"], p["pmid"]) for r in runs.values() for p in r["retrieved"]} - set(rel))
    wb = Workbook()
    ws = wb.active
    ws.title = "补判"
    ws.append(["题号", "PMID", "年份", "标题", "问题", "是否相关（是/否）"])
    qtext = {r["id"]: r["question"] for r in runs.values()}
    for qid, pm in todo:
        p = conn.execute("SELECT title, year FROM papers WHERE pmid = ?", (pm,)).fetchone()
        ws.append([qid, pm, p["year"], p["title"], qtext[qid], ""])
    style(ws, [6, 10, 6, 70, 45, 12], [6])
    wb.save(POOL)
    print(f"需要补判 {len(todo)} 篇（系统检索到、但不在候选证据表里的），已生成 {POOL.relative_to(ROOT)}")
    print(f"填好后另存为 {POOL_DONE.name}")


def review(n=20):
    """抽样：只抽范围内题，三个系统大致均匀。"""
    judged = json.loads(JUDGE.read_text(encoding="utf-8"))
    runs = json.loads(RUNS.read_text(encoding="utf-8"))
    points = {}
    for row in load_workbook(GOLD, read_only=True)["题目"].iter_rows(min_row=2, values_only=True):
        if row[0] and row[7]:
            points[row[0]] = [x.strip() for x in str(row[7]).splitlines() if x.strip()]
    items = [(qid, m) for qid, j in judged.items() if j["scope"] == "in" for m in j["results"]]
    random.Random(2026).shuffle(items)
    wb = Workbook()
    ws = wb.active
    ws.title = "复核"
    ws.append(["题号", "系统", "问题", "回答", "要点编号", "参考要点", "模型判定", "你的判定（覆盖/部分覆盖/未覆盖）"])
    for qid, m in items[:n]:
        for v in judged[qid]["results"][m]["points"]:
            i = v["point"]
            if 1 <= i <= len(points[qid]):
                ws.append([qid, NAME[m], runs[f"{qid}|{m}"]["question"], runs[f"{qid}|{m}"]["answer"],
                           i, points[qid][i - 1], v["verdict"], ""])
    style(ws, [6, 12, 30, 80, 6, 40, 10, 14], [8])
    wb.save(REVIEW)
    print(f"已生成 {REVIEW.relative_to(ROOT)}：{n} 份回答、{ws.max_row - 1} 条要点判定，请填最后一列")


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def score():
    questions = {q["id"]: q for q in yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))}
    runs = json.loads(RUNS.read_text(encoding="utf-8"))
    judged = json.loads(JUDGE.read_text(encoding="utf-8")) if JUDGE.exists() else {}
    rel = load_relevance()

    # 每个（题，系统）算一组指标
    rows = []
    for qid, q in questions.items():
        for m in MODES:
            r = runs.get(f"{qid}|{m}")
            if not r:
                continue
            row = {"qid": qid, "mode": m, "category": q["category"], "source": q["source"], "scope": q["scope"],
                   "invalid": len(r["invalid_citations"]), "n_cited": len(r["cited"])}
            top5 = [p["pmid"] for p in r["retrieved"][:5]]
            if top5 and q["scope"] == "in":
                known = [rel[(qid, p)] for p in top5 if (qid, p) in rel]
                row["p5"] = sum(known) / len(top5)
                row["unjudged"] = len(top5) - len(known)
            j = judged.get(qid, {}).get("results", {}).get(m)
            if j and q["scope"] == "in":
                n = judged[qid]["n_points"]
                got = {v["point"]: COV.get(v["verdict"], 0) for v in j["points"]}
                row["coverage"] = sum(got.get(i, 0) for i in range(1, n + 1)) / n if n else None
                cits = [SUP.get(c["verdict"], 0) for c in j["citations"]]
                row["support"] = sum(cits) / len(cits) if cits else None
                row["contradictions"] = j["contradictions"]
            if j and q["scope"] == "out":
                row["refused"] = j["refused"]
                row["substantive"] = j["substantive"]
            rows.append(row)

    def mean(rs, key):
        vals = [r[key] for r in rs if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    lines = ["# 问答评估结果（自动生成）", "",
             f"题库 {len(questions)} 题（范围内 {sum(q['scope'] == 'in' for q in questions.values())}、"
             f"范围外 {sum(q['scope'] == 'out' for q in questions.values())}）；"
             f"已打分 {len(judged)} 题。", "",
             "## 总体（范围内题）", "",
             "| 系统 | 检索 P@5 | 要点覆盖率 | 引用支持率 | 无效引用 | 矛盾结论（每题） |",
             "|---|---|---|---|---|---|"]
    by_mode = defaultdict(list)
    for r in rows:
        by_mode[r["mode"]].append(r)
    for m in MODES:
        rs = [r for r in by_mode[m] if r["scope"] == "in"]
        lines.append(f"| {NAME[m]} | {pct(mean(rs, 'p5'))} | {pct(mean(rs, 'coverage'))} | "
                     f"{pct(mean(rs, 'support'))} | {sum(r['invalid'] for r in rs)} | "
                     f"{(mean(rs, 'contradictions') or 0):.2f} |")
    unj = sum(r.get("unjudged", 0) for r in rows)
    if unj:
        lines.append(f"\n> ⚠️ 检索结果中有 {unj} 篇尚未人工判定相关性，P@5 按「不相关」计，结果偏低。运行 `qa_score pool` 补判。")

    lines += ["", "## 范围外题（6 题）", "", "| 系统 | 拒答率 | 仍给出实质结论 |", "|---|---|---|"]
    for m in MODES:
        rs = [r for r in by_mode[m] if r["scope"] == "out" and "refused" in r]
        lines.append(f"| {NAME[m]} | {pct(mean(rs, 'refused'))} | {pct(mean(rs, 'substantive'))} |")

    for title, key in [("按题型：要点覆盖率", "category"), ("按出题人：要点覆盖率", "source")]:
        groups = sorted({r[key] for r in rows if r["scope"] == "in"})
        lines += ["", f"## {title}", "", "| 系统 | " + " | ".join(groups) + " |",
                  "|---|" + "---|" * len(groups)]
        for m in MODES:
            cells = [pct(mean([r for r in by_mode[m] if r["scope"] == "in" and r[key] == g], "coverage"))
                     for g in groups]
            lines.append(f"| {NAME[m]} | " + " | ".join(cells) + " |")

    lines += ["", "## 逐题明细（要点覆盖率 A / B / C）", "", "| 题号 | 题型 | 出题人 | A | B | C |",
              "|---|---|---|---|---|---|"]
    for qid, q in questions.items():
        if q["scope"] != "in":
            continue
        cells = [pct(next((r.get("coverage") for r in rows if r["qid"] == qid and r["mode"] == m), None))
                 for m in MODES]
        lines.append(f"| {qid} | {q['category']} | {q['source']} | " + " | ".join(cells) + " |")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:16]))
    print(f"\n完整结果已保存到 {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    {"pool": pool, "review": review, "score": score}[cmd]()
