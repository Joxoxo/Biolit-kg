"""M6 验证集：在 20 篇"从没看过"的文献上，盲评比较 v5 和 v6。

为什么需要：v6 的规则是根据那 40 篇的错误设计的，又在同样的 40 篇上测试，结果会偏乐观（过拟合）。
验证集换一批新文献，才能确认改进是真的。

为什么"盲评"：把 v5 和 v6 的结果合并去重、打乱顺序放进同一张表，表里不显示每条来自哪个版本，
标注时就不会不自觉地偏向某一方。

用法（在 biolit-kg 文件夹下，按顺序）：
    python -m biolit.eval.holdout sample      # ① 抽 20 篇新文献 → data/annotations/holdout_pmids.txt
    python -m biolit.extract.run --pmids-file data/annotations/holdout_pmids.txt   # ② 用 v6 抽取
    python -m biolit.normalize.run            # ③ 标准化
    python -m biolit.eval.holdout sheet       # ④ 生成盲评标注表 → annotation_holdout.xlsx
    （人工标注，另存为 annotation_holdout_已标注.xlsx）
    python -m biolit.eval.holdout score       # ⑤ 两个版本在同一份标准答案上打分
"""
import json
import random
import sys
from collections import Counter, defaultdict

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from biolit.db import ROOT, get_connection
from biolit.eval.compare import REL2ZH, matches
from biolit.eval.score import prf

ANN = ROOT / "data" / "annotations"
HOLDOUT = ANN / "holdout_pmids.txt"
SHEET = ANN / "annotation_holdout.xlsx"
DONE = ANN / "annotation_holdout_已标注.xlsx"
VERSIONS = ("v5", "v6")
SEED = 2026                     # 和训练集（种子 42）不同
N_WITH, N_WITHOUT = 16, 4


def sample():
    conn = get_connection()
    used = {int(x) for x in (ANN / "sample_pmids.txt").read_text().split()}
    rows = conn.execute(
        "SELECT e.pmid, e.study_type, (SELECT COUNT(*) FROM relations r WHERE r.pmid = e.pmid "
        "AND r.prompt_version = 'v5') AS n FROM extractions e WHERE e.prompt_version = 'v5' AND e.status = 'ok'"
    ).fetchall()
    rng = random.Random(SEED)
    by_type, without = defaultdict(list), []
    for r in rows:
        if r["pmid"] in used:
            continue                                     # 排除已经用过的 40 篇
        (by_type[r["study_type"]] if r["n"] > 0 else without).append(r["pmid"])
    picked = []
    for t in sorted(by_type):                            # 每类研究至少 1 篇
        picked.append(rng.choice(sorted(by_type[t])))
    rest = sorted(p for t in by_type for p in by_type[t] if p not in picked)
    picked += rng.sample(rest, N_WITH - len(picked))
    picked += rng.sample(sorted(without), N_WITHOUT)
    HOLDOUT.write_text("\n".join(map(str, picked)) + "\n")
    types = Counter(conn.execute("SELECT study_type FROM extractions WHERE pmid=? AND prompt_version='v5'",
                                 (p,)).fetchone()[0] for p in picked)
    print(f"验证集 {len(picked)} 篇（与之前 40 篇无重叠）：{dict(types)} → {HOLDOUT.relative_to(ROOT)}")


def union_rows(conn, pmid):
    """把 v5、v6 对同一篇的抽取合并去重：能互相对上的算同一条，记录它来自哪些版本。"""
    merged = []
    for v in VERSIONS:
        for r in conn.execute(
                "SELECT id, subject, relation, object, comparator, effect, population, evidence, "
                "subject_norm, object_norm FROM relations WHERE pmid = ? AND prompt_version = ?", (pmid, v)):
            key = {"s": r["subject_norm"], "rel": r["relation"], "o": r["object_norm"]}
            hit = next((m for m in merged if matches(key, m["key"])), None)
            if hit:
                hit["ids"].setdefault(v, []).append(r["id"])
            else:
                merged.append({"key": key, "row": r, "ids": {v: [r["id"]]}})
    return merged


def sheet():
    conn = get_connection()
    pmids = [int(x) for x in HOLDOUT.read_text().split()]
    missing = [v for v in VERSIONS if conn.execute(
        f"SELECT COUNT(*) FROM extractions WHERE prompt_version = ? AND status='ok' AND pmid IN "
        f"({','.join('?' * len(pmids))})", (v, *pmids)).fetchone()[0] < len(pmids)]
    if missing:
        raise SystemExit(f"{missing} 还没有跑完这 20 篇，请先运行第 ② ③ 步")

    rng = random.Random(SEED)
    wb = Workbook()
    ws = wb.active
    ws.title = "标注"
    ws.append(["序号", "PMID", "", "主体", "关系", "客体", "对照药", "效果", "人群", "证据句", "判定", "备注", "key"])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="4A6FA5")
    for col, w in zip("ABCDEFGHIJKLM", [6, 11, 8, 22, 10, 26, 16, 26, 22, 60, 11, 30, 6]):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["M"].hidden = True                # 隐藏列：记录来源版本，标注时看不到
    dv = DataValidation(type="list", formula1='"正确,部分正确,错误,漏抽"', allow_blank=True)
    ws.add_data_validation(dv)
    wrap, grey = Alignment(wrap_text=True, vertical="top"), PatternFill("solid", fgColor="E8EEF6")

    keys, n = {}, 0
    for i, pmid in enumerate(pmids, 1):
        p = conn.execute("SELECT title, abstract FROM papers WHERE pmid = ?", (pmid,)).fetchone()
        ws.append([i, pmid, "", p["title"]])
        r0 = ws.max_row
        ws.cell(r0, 2).hyperlink = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        ws.merge_cells(start_row=r0, start_column=4, end_row=r0, end_column=12)
        for c in ws[r0]:
            c.fill, c.font, c.alignment = grey, Font(bold=True), wrap
        ws.append(["", "", "摘要", p["abstract"]])
        r0 = ws.max_row
        ws.merge_cells(start_row=r0, start_column=4, end_row=r0, end_column=12)
        ws.cell(r0, 4).alignment = wrap
        ws.row_dimensions[r0].height = min(409, 15 * (len(p["abstract"]) // 170 + 2))

        merged = union_rows(conn, pmid)
        rng.shuffle(merged)                                # 打乱顺序，看不出哪些是新版本加的
        for m in merged:
            n += 1
            r = m["row"]
            ws.append(["", pmid, "", r["subject"], REL2ZH.get(r["relation"], r["relation"]), r["object"],
                       r["comparator"], r["effect"], r["population"], r["evidence"], "", "", n])
            keys[n] = m["ids"]
            for c in ws[ws.max_row]:
                c.alignment = wrap
            dv.add(ws.cell(ws.max_row, 11))
        for _ in range(3):
            ws.append(["", pmid, "（漏抽）"])
            ws.cell(ws.max_row, 3).font = Font(color="999999")
            dv.add(ws.cell(ws.max_row, 11))

    wb.save(SHEET)
    (ANN / "holdout_keys.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    print(f"盲评标注表：{SHEET.relative_to(ROOT)}（{len(pmids)} 篇，合并去重后 {n} 条待判定）")
    print("标完后请另存为 annotation_holdout_已标注.xlsx")


def score():
    keys = {int(k): v for k, v in json.loads((ANN / "holdout_keys.json").read_text(encoding="utf-8")).items()}
    ws = load_workbook(DONE, read_only=True)["标注"]
    judged, missed = {}, 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[10] == "漏抽":
            missed += 1
        elif row[12] and row[10]:
            judged[int(row[12])] = row[10]
    unjudged = len(keys) - len(judged)

    lines = ["# 验证集：v5 vs v6（20 篇新文献，盲评）\n",
             f"- 合并去重后 {len(keys)} 条，人工补充漏抽 {missed} 条" + (f"；⚠️ {unjudged} 条未判定" if unjudged else ""),
             "\n| 版本 / 口径 | 抽出 | 抽对 | Precision | Recall | F1 |", "|---|---|---|---|---|---|"]
    for lenient in (False, True):
        ok = {"正确", "部分正确"} if lenient else {"正确"}
        gold = sum(j in ok for j in judged.values()) + missed      # 标准答案 = 判对的 + 漏抽
        for v in VERSIONS:
            mine = [k for k, ids in keys.items() if v in ids]
            c = sum(judged.get(k) in ok for k in mine)
            s = prf(c, len(mine), gold - c)
            lines.append(f"| {v} {'宽松' if lenient else '严格'} | {len(mine)} | {c} | "
                         f"{s['precision']:.1%} | {s['recall']:.1%} | {s['f1']:.2f} |")
    lines.append("\n> 标准答案 = 任一版本抽对的关系 + 两个版本都没抽到、由人工补充的漏抽。")
    out = ANN / "eval_holdout_v5_v6.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n报告：{out.relative_to(ROOT)}")


if __name__ == "__main__":
    {"sample": sample, "sheet": sheet, "score": score}[sys.argv[1] if len(sys.argv) > 1 else "sample"]()
