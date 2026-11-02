"""M6 第 3 步：用 v5 的人工标注（标准答案）给新版本自动打分，只把对不上的交给人工判断。

标准答案 = v5 中判为"正确/部分正确"的关系 + 人工补充的"漏抽"关系
已知错误 = v5 中判为"错误"的关系

新版本的每条关系：
  能对上标准答案 → 自动判"正确"（若对上的是 v5"部分正确"的条目，交人工复核：可能已经改好了）
  能对上已知错误 → 自动判"错误"
  对不上         → 交给人工判断

"对得上"的标准：同一篇文献、关系类型相同，且主体和客体标准化后相同或互相包含
（如 "rivaroxaban 2.5 mg bid" 和 "rivaroxaban"、"cyp3a4/5" 和 "cyp3a4"）

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.eval.compare v6
输出：data/annotations/annotation_v6_待复核.xlsx（只含需要人工判断的条目）
"""
import sys
from collections import defaultdict

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from biolit.db import ROOT, get_connection
from biolit.normalize.synonyms import Normalizer

GOLD_FILE = ROOT / "data" / "annotations" / "annotation_v5_已标注.xlsx"
GOLD_VERSION = "v5"
ZH2REL = {"增加风险": "increases_risk", "降低风险": "decreases_risk", "相互作用": "interacts_with",
          "抑制": "inhibits", "诱导": "induces", "被代谢": "metabolized_by", "禁用": "contraindicated_in",
          "被转运": "transported_by"}
REL2ZH = {v: k for k, v in ZH2REL.items()}
REVIEW_CHOICES = ["正确-对应标准答案", "正确-新关系", "部分正确", "错误"]


def load_gold(conn, norm):
    """读取 v5 标注表，返回 {pmid: {"pos": [...], "neg": [...]}}，每项是 dict(s, rel, o, label, text)。"""
    ws = load_workbook(GOLD_FILE, read_only=True)["标注"]
    gold = defaultdict(lambda: {"pos": [], "neg": []})
    for row in ws.iter_rows(min_row=2, values_only=True):
        pmid, subj, rel, obj, judge, rel_id = row[1], row[3], row[4], row[5], row[10], row[12]
        if not pmid or row[0] not in (None, "") or row[2] == "摘要" or not judge:
            continue
        if rel_id:   # 模型抽出的关系：用数据库里标准化后的名字
            r = conn.execute("SELECT subject_norm, relation, object_norm FROM relations WHERE id = ?",
                             (int(rel_id),)).fetchone()
            item = {"s": r["subject_norm"], "rel": r["relation"], "o": r["object_norm"], "label": judge,
                    "text": f"{subj} {rel} {obj}"}
        else:        # 人工补充的漏抽
            item = {"s": norm(subj) if subj else None, "rel": ZH2REL.get(rel), "o": norm(obj) if obj else None,
                    "label": "漏抽", "text": f"{subj or ''} {rel or ''} {obj or ''} | {row[9] or ''}".strip()}
        gold[int(pmid)]["neg" if judge == "错误" else "pos"].append(item)
    return gold


def _close(a, b) -> bool:
    return bool(a and b) and (a == b or a in b or b in a)


def matches(new, g) -> bool:
    return new["rel"] == g["rel"] and _close(new["s"], g["s"]) and _close(new["o"], g["o"])


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "v6"
    conn, norm = get_connection(), Normalizer()
    gold = load_gold(conn, norm)
    pmids = list(gold.keys()) or [int(x) for x in open(ROOT / "data/annotations/sample_pmids.txt").read().split()]

    results = []   # 每条新关系的自动判定结果
    found = defaultdict(set)   # 每篇文献中被新版本命中的标准答案序号
    for pmid in pmids:
        rows = conn.execute(
            "SELECT id, subject, relation, object, subject_norm, object_norm, comparator, effect, evidence "
            "FROM relations WHERE pmid = ? AND prompt_version = ? ORDER BY id", (pmid, version)).fetchall()
        for r in rows:
            new = {"s": r["subject_norm"], "rel": r["relation"], "o": r["object_norm"]}
            hit = next((i for i, g in enumerate(gold[pmid]["pos"]) if i not in found[pmid] and matches(new, g)), None)
            if hit is not None:
                found[pmid].add(hit)
                g = gold[pmid]["pos"][hit]
                auto = "待复核（v5 部分正确）" if g["label"] == "部分正确" else "正确（自动）"
                ref = g["text"]
            elif any(matches(new, g) for g in gold[pmid]["neg"]):
                auto, ref = "错误（自动）", "与 v5 已判错误的关系相同"
            else:
                auto, ref = "待判定", ""
            results.append({"pmid": pmid, "row": r, "auto": auto, "ref": ref})

    # ---------- 生成待复核表：只放需要人工判断的文献 ----------
    pending = [x for x in results if x["auto"].startswith("待")]
    wb = Workbook()
    ws = wb.active
    ws.title = "复核"
    ws.append(["PMID", "主体", "关系", "客体", "对照药", "效果", "证据句", "自动判定", "判定", "备注", "rel_id"])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="4A6FA5")
    for col, w in zip("ABCDEFGHIJK", [11, 22, 10, 26, 16, 26, 60, 18, 20, 30, 8]):
        ws.column_dimensions[col].width = w
    dv = DataValidation(type="list", formula1=f'"{",".join(REVIEW_CHOICES)}"', allow_blank=True)
    ws.add_data_validation(dv)
    wrap = Alignment(wrap_text=True, vertical="top")
    grey = PatternFill("solid", fgColor="E8EEF6")

    for pmid in sorted({x["pmid"] for x in pending}):
        p = conn.execute("SELECT title, abstract FROM papers WHERE pmid = ?", (pmid,)).fetchone()
        ws.append([pmid, p["title"]])
        r0 = ws.max_row
        ws.merge_cells(start_row=r0, start_column=2, end_row=r0, end_column=10)
        ws.cell(r0, 1).hyperlink = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        for c in ws[r0]:
            c.fill, c.font, c.alignment = grey, Font(bold=True), wrap
        ws.append(["", p["abstract"]])
        r0 = ws.max_row
        ws.merge_cells(start_row=r0, start_column=2, end_row=r0, end_column=10)
        ws.cell(r0, 2).alignment = wrap
        ws.row_dimensions[r0].height = min(409, 15 * (len(p["abstract"]) // 170 + 2))
        # 参考：这篇文献里还没被新版本命中的标准答案（帮助判断"对应标准答案"还是"新关系"）
        left = [g["text"] for i, g in enumerate(gold[pmid]["pos"]) if i not in found[pmid]]
        if left:
            ws.append(["", "未命中的标准答案（参考）：\n" + "\n".join(f"· {t}" for t in left)])
            r0 = ws.max_row
            ws.merge_cells(start_row=r0, start_column=2, end_row=r0, end_column=10)
            ws.cell(r0, 2).alignment, ws.cell(r0, 2).font = wrap, Font(color="7A5C00")
            ws.row_dimensions[r0].height = 15 * (len(left) + 1)
        for x in (x for x in pending if x["pmid"] == pmid):
            r = x["row"]
            ws.append([pmid, r["subject"], REL2ZH.get(r["relation"], r["relation"]), r["object"], r["comparator"],
                       r["effect"], r["evidence"], x["auto"], "", x["ref"], r["id"]])
            for c in ws[ws.max_row]:
                c.alignment = wrap
            dv.add(ws.cell(ws.max_row, 9))

    out = ROOT / "data" / "annotations" / f"annotation_{version}_待复核.xlsx"
    wb.save(out)

    # ---------- 自动部分的结果汇总（存成 JSON，人工复核后由 score_compare 合并计算） ----------
    import json
    auto_file = ROOT / "data" / "annotations" / f"auto_{version}.json"
    auto_file.write_text(json.dumps({
        "version": version,
        "results": [{"pmid": x["pmid"], "rel_id": x["row"]["id"], "auto": x["auto"]} for x in results],
        "gold_total": sum(len(g["pos"]) for g in gold.values()),
        "gold_found_auto": sum(len(v) for v in found.values()),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter
    cnt = Counter(x["auto"] for x in results)
    print(f"{version} 共抽出 {len(results)} 条；自动判定：{dict(cnt)}")
    print(f"标准答案 {sum(len(g['pos']) for g in gold.values())} 条，自动命中 {sum(len(v) for v in found.values())} 条")
    print(f"需要人工判断 {len(pending)} 条 → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
