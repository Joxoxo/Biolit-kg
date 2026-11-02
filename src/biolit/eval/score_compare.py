"""M6 第 4 步：合并"自动判定 + 人工复核"，计算新版本的指标，并与 v5 在同一标准答案上对比。

标准答案的扩充：新版本抽出、经人工确认的"正确-新关系"，说明 v5 标注时漏标了，
所以把它们加进标准答案，v5 和新版本都用扩充后的标准答案重新计算 Recall，保证对比公平。

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.eval.score_compare v6
需要：data/annotations/auto_v6.json（compare 生成）和 annotation_v6_已复核.xlsx（人工复核后）
输出：data/annotations/eval_compare_v5_v6.md
"""
import json
import sys
from collections import Counter

from openpyxl import load_workbook

from biolit.db import ROOT
from biolit.eval.score import load_annotations, prf

ANN = ROOT / "data" / "annotations"


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "v6"
    auto = json.loads((ANN / f"auto_{version}.json").read_text(encoding="utf-8"))
    ws = load_workbook(ANN / f"annotation_{version}_已复核.xlsx", read_only=True)["复核"]
    review = {int(r[10]): r[8] for r in ws.iter_rows(min_row=2, values_only=True) if r[10]}

    # ---------- 新版本：每条关系的最终判定 ----------
    final = Counter()
    for x in auto["results"]:
        j = x["auto"] if not x["auto"].startswith("待") else review.get(x["rel_id"], "未复核")
        final[j] += 1
    correct_strict = final["正确（自动）"] + final["正确-对应标准答案"] + final["正确-新关系"]
    correct_lenient = correct_strict + final["部分正确"]
    new_gold = final["正确-新关系"]                                # 扩充进标准答案的条数
    gold = auto["gold_total"] + new_gold                         # 扩充后的标准答案总数

    # ---------- v5：用扩充后的标准答案重新计算 ----------
    papers = load_annotations(ANN / "annotation_v5_已标注.xlsx")
    v5_rows = [m for p in papers for m in p["model"]]
    v5_strict = sum(m["judge"] == "正确" for m in v5_rows)
    v5_lenient = v5_strict + sum(m["judge"] == "部分正确" for m in v5_rows)

    def row(name, c, e):
        s = prf(c, e, gold - c)
        return f"| {name} | {e} | {c} | {s['precision']:.1%} | {s['recall']:.1%} | {s['f1']:.2f} |"

    lines = [f"# 提示词 v5 vs {version}（40 篇，同一模型 gemini-3.5-flash-lite）\n",
             f"- 标准答案：v5 标注 {auto['gold_total']} 条 + {version} 新发现并经人工确认 {new_gold} 条 = **{gold} 条**",
             f"- {version} 判定分布：{dict(final)}" + ("；⚠️ 有未复核条目" if final["未复核"] else ""),
             "\n| 版本 / 口径 | 抽出 | 抽对 | Precision | Recall | F1 |", "|---|---|---|---|---|---|",
             row("v5 严格", v5_strict, len(v5_rows)), row("v5 宽松", v5_lenient, len(v5_rows)),
             row(f"{version} 严格", correct_strict, len(auto["results"])),
             row(f"{version} 宽松", correct_lenient, len(auto["results"])),
             "\n> 严格：只算'正确'；宽松：'部分正确'也算对。Recall 的分母是扩充后的标准答案。"]
    out = ANN / f"eval_compare_v5_{version}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n报告：{out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
