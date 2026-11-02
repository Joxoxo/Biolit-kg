"""M6 第 2 步：根据人工标注计算抽取质量指标，并生成评估报告。

指标定义（以人工标注为标准答案）：
  Precision = 判对的条数 / 模型抽出的总条数        —— 抽出来的有多少是对的
  Recall    = 判对的条数 / (模型抽对的 + 漏抽的)    —— 该抽的有多少被抽到了
  F1        = Precision 和 Recall 的调和平均

两种口径：
  严格：只有"正确"算对
  宽松："正确"和"部分正确"都算对（主要关系对，只是次要字段有瑕疵）

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.eval.score
    python -m biolit.eval.score data/annotations/其他标注文件.xlsx
输出：data/annotations/eval_report_<文件名>.md
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook

from biolit.db import ROOT

DEFAULT = ROOT / "data" / "annotations" / "annotation_v5_已标注.xlsx"


def load_annotations(path: Path) -> list[dict]:
    """读取标注表，返回每篇文献的 {pmid, study_type, model: [...], missed: [...]}。只读，不修改文件。"""
    ws = load_workbook(path, read_only=True)["标注"]
    papers, cur = [], None
    for row in ws.iter_rows(min_row=2, values_only=True):
        idx, pmid, col_c, subj, rel, obj = row[:6]
        judge, note, rel_id = row[10], row[11], row[12]
        if col_c == "摘要":
            continue
        if idx not in (None, ""):                       # 文献标题行
            cur = {"pmid": pmid, "study_type": col_c, "model": [], "missed": []}
            papers.append(cur)
        elif rel_id:                                     # 模型抽取的关系
            cur["model"].append({"relation": rel, "judge": judge, "note": note})
        elif judge == "漏抽":                            # 人工补充的漏抽
            cur["missed"].append({"relation": rel, "note": note})
    return papers


def prf(correct: int, extracted: int, missed: int) -> dict:
    p = correct / extracted if extracted else 0.0
    r = correct / (correct + missed) if correct + missed else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f, "correct": correct, "extracted": extracted, "missed": missed}


def score(papers: list[dict], lenient: bool) -> dict:
    ok = {"正确", "部分正确"} if lenient else {"正确"}
    rows = [m for p in papers for m in p["model"]]
    correct = sum(m["judge"] in ok for m in rows)
    missed = sum(len(p["missed"]) for p in papers)
    # 严格口径下，"部分正确"的那条正确关系并没有被准确抽到，所以同时算作漏抽（标准答案里它仍然存在）
    if not lenient:
        missed += sum(m["judge"] == "部分正确" for m in rows)
    return prf(correct, len(rows), missed)


def breakdown(papers, key_fn, lenient=True) -> dict:
    """按某个维度分组计算指标，如关系类型、研究类型。"""
    ok = {"正确", "部分正确"} if lenient else {"正确"}
    groups = defaultdict(lambda: {"c": 0, "e": 0, "m": 0})
    for p in papers:
        for m in p["model"]:
            g = groups[key_fn(p, m)]
            g["e"] += 1
            g["c"] += m["judge"] in ok
        for m in p["missed"]:
            groups[key_fn(p, m)]["m"] += 1
    return {k: prf(v["c"], v["e"], v["m"]) for k, v in groups.items()}


def fmt_table(title: str, rows: dict) -> list[str]:
    out = [f"\n### {title}\n", "| 分组 | 模型抽出 | 抽对 | 漏抽 | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|"]
    for k, s in sorted(rows.items(), key=lambda x: -(x[1]["extracted"] + x[1]["missed"])):
        out.append(f"| {k} | {s['extracted']} | {s['correct']} | {s['missed']} | "
                   f"{s['precision']:.1%} | {s['recall']:.1%} | {s['f1']:.2f} |")
    return out


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    papers = load_annotations(path)

    unjudged = sum(1 for p in papers for m in p["model"] if not m["judge"])
    judges = Counter(m["judge"] for p in papers for m in p["model"] if m["judge"])
    n_missed = sum(len(p["missed"]) for p in papers)
    strict, lenient = score(papers, False), score(papers, True)

    lines = [f"# 抽取评估报告：{path.name}\n",
             f"- 标注文献：{len(papers)} 篇；模型抽出关系 {sum(len(p['model']) for p in papers)} 条，"
             f"人工补充漏抽 {n_missed} 条",
             f"- 判定分布：{dict(judges)}" + (f"；⚠️ 尚有 {unjudged} 条未判定" if unjudged else ""),
             "\n## 总体指标\n",
             "| 口径 | Precision | Recall | F1 |", "|---|---|---|---|",
             f"| 严格（只算正确） | {strict['precision']:.1%} | {strict['recall']:.1%} | {strict['f1']:.2f} |",
             f"| 宽松（含部分正确） | {lenient['precision']:.1%} | {lenient['recall']:.1%} | {lenient['f1']:.2f} |",
             "\n## 分组指标（宽松口径）"]
    lines += fmt_table("按研究类型", breakdown(papers, lambda p, m: p["study_type"]))
    lines += fmt_table("按关系类型", breakdown(papers, lambda p, m: m["relation"] or "（未填）"))

    # 漏抽最多的文献
    top = sorted(papers, key=lambda p: -len(p["missed"]))[:5]
    lines += ["\n## 漏抽最多的文献\n", "| PMID | 研究类型 | 漏抽条数 |", "|---|---|---|"]
    lines += [f"| {p['pmid']} | {p['study_type']} | {len(p['missed'])} |" for p in top if p["missed"]]

    # 备注汇总：错误类型
    notes = Counter()
    for p in papers:
        for m in p["model"]:
            if m["note"] and (m["judge"] != "正确" or "超出" in str(m["note"])):
                notes[f"[{m['judge']}] {m['note']}"] += 1
        for m in p["missed"]:
            if m["note"]:
                notes[f"[漏抽] {m['note']}"] += 1
    lines += ["\n## 备注中的问题类型（非'正确'条目 + 结论夸大）\n"]
    lines += [f"- ({n}) {note}" for note, n in notes.most_common(20)]

    out = path.parent / f"eval_report_{path.stem}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"\n完整报告：{out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
