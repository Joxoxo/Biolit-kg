"""说明书交叉验证 · 第 3 步：把文献图谱里的关系和说明书逐条比对。

比对单位（同一对只算一次，文献数取所有相关关系的并集）：
- 不良反应：（药物, 不良事件），来自图谱中"药物 增加风险 不良事件"的关系。比较方向不重要，只要文献报道了这种风险
- 相互作用：（药物, 合用药），来自"相互作用 / 抑制 / 诱导"关系
- 药代：（药物, 酶或转运体），来自"被代谢 / 被转运"关系
"降低风险""相比华法林"这类疗效比较结论，说明书里没有对应内容，不参与比对。

比对结果：
- 说明书已收录：说明书直接写了这一项
- 上位概念收录：说明书写的是更宽的概念，如文献"消化道出血"、说明书"出血"（借用同义词表里的上下级关系）
- 类别收录：说明书写的是药物类别，如文献"酮康唑"、说明书"P-gp 和强效 CYP3A4 联合抑制剂"
- 原文提及（抽取遗漏）：大模型没抽出来，但说明书原文里能搜到这个词 —— 不调用大模型的兜底检查
- 说明书不一致：说明书明确写"无需调整剂量 / 无临床相关相互作用"，而文献报道了相互作用
- 仅文献报道：说明书里没找到 —— 潜在信号，但也可能只是说明书没更新、或抽取遗漏，需要人工确认

运行（在 biolit-kg 文件夹下，需先运行 python -m biolit.label.extract）：
    python -m biolit.label.compare           # 比对
    python -m biolit.label.compare review    # 生成人工审核表（说明书不一致 + 仅文献报道的相互作用 / 药代）
输出：data/processed/label_crosscheck.json（给网页用）、data/annotations/label_crosscheck.md（结果汇总）
"""
import json
import re
from collections import defaultdict

from biolit.db import ROOT
from biolit.graph.build import GRAPH_PATH
from biolit.normalize.synonyms import Normalizer

FACTS = ROOT / "data" / "processed" / "label_facts.json"
LABEL_DIR = ROOT / "data" / "raw" / "labels"
OUT_JSON = ROOT / "data" / "processed" / "label_crosscheck.json"
OUT_MD = ROOT / "data" / "annotations" / "label_crosscheck.md"
REVIEW = ROOT / "data" / "annotations" / "label_review_待审核.xlsx"

DRUGS = ["apixaban", "rivaroxaban", "dabigatran", "edoxaban", "warfarin", "clopidogrel", "ticagrelor"]
AE_RELATIONS = {"increases_risk"}
DDI_RELATIONS = {"interacts_with", "inhibits", "induces"}
PK_RELATIONS = {"metabolized_by", "transported_by"}

# 说明书里的写法和同义词表没覆盖到的，在这里补充（只用于比对，不改动图谱）
ALIASES = {"cyp3a4/5": "cyp3a4", "cyp3a": "cyp3a4", "nsaids": "nsaid", "nsaiads": "nsaid",
           "nonsteroidal anti-inflammatory drugs": "nsaid", "non-steroidal anti-inflammatory drugs": "nsaid",
           "st. john’s wort": "st. john's wort", "rifampicin": "rifampin", "thromboembolic events": "thrombotic event",
           "thrombotic events after discontinuation": "thrombotic event",
           "thrombotic events after premature discontinuation": "thrombotic event"}
# 说明书常写药物类别。下面列出常见类别包含的具体药物，用来判断"类别收录"。
# 酶抑制剂 / 诱导剂的归类参考 FDA 公布的"药物相互作用示例名单"（Drug Development and Drug Interactions:
# Table of Substrates, Inhibitors and Inducers）。键是说明书 target 里必须同时出现的关键词。
CLASS_MEMBERS = {
    ("antiplatelet",): ["aspirin", "clopidogrel", "ticagrelor", "prasugrel", "low-dose aspirin", "anti-platelets"],
    ("anticoagulant",): ["warfarin", "heparin", "enoxaparin", "low-molecular-weight heparin", "apixaban",
                         "rivaroxaban", "dabigatran", "edoxaban"],
    ("hemostasis",): ["aspirin", "clopidogrel", "ticagrelor", "heparin", "nsaid", "antidepressant"],
    ("nsaid",): ["ibuprofen", "naproxen", "diclofenac", "celecoxib"],
    ("serotonin",): ["fluoxetine", "sertraline", "citalopram", "escitalopram", "paroxetine", "antidepressant"],
    ("p-gp", "inhibitor"): ["verapamil", "dronedarone", "amiodarone", "quinidine", "ketoconazole", "itraconazole",
                            "clarithromycin", "erythromycin", "cyclosporine", "ritonavir", "cobicistat",
                            "posaconazole", "ticagrelor"],
    ("cyp3a", "inhibitor"): ["ketoconazole", "itraconazole", "posaconazole", "voriconazole", "clarithromycin",
                             "ritonavir", "cobicistat", "fluconazole", "erythromycin", "diltiazem", "verapamil",
                             "dronedarone"],
    ("inducer",): ["rifampin", "carbamazepine", "phenytoin", "st. john's wort", "enzalutamide", "apalutamide"],
}
# 文献里出血的写法有几十种（BARC 分型、术后出血、月经过多……），同义词表覆盖不全；
# 名称里含这些词的不良事件，都视为说明书"出血（bleeding）"的下位概念
BLEED_WORDS = ("bleed", "hemorrhag", "haemorrhag", "gib", "hmb", "ppb", "aub", "hematoma", "menstrua")
NEGATIVE = ("no dose adjustment", "no clinically relevant", "not clinically relevant", "no significant")


def main():
    norm = Normalizer()

    def n(x: str) -> str:
        x = norm(x) or ""
        return ALIASES.get(x, x)

    # 上位概念：子类 → 所有祖先（如 gastrointestinal bleeding → bleeding）
    def ancestors(x: str) -> set[str]:
        out, stack = set(), [x]
        while stack:
            for p in norm.hierarchy.get(stack.pop(), []):
                if p not in out:
                    out.add(p)
                    stack.append(p)
        return out

    # ---------- 说明书：每种药的已知项 ----------
    facts = [r for rows in json.loads(FACTS.read_text(encoding="utf-8")).values() for r in rows]
    label = defaultdict(list)          # (药物, 类别) → [(target, examples, effect, evidence)]
    for f in facts:
        cat = {"adverse_reaction": "ae", "contraindication": "ae", "interaction": "ddi",
               "pharmacokinetics": "pk"}[f["category"]]
        label[(f["drug"], cat)].append({"target": n(f["target"]), "examples": [n(e) for e in f["examples"]],
                                        "effect": (f["effect"] or "").lower(), "evidence": f["evidence"]})

    # 说明书原文（全部章节拼起来，小写），用于兜底搜索
    raw = {p.stem: " ".join(json.loads(p.read_text(encoding="utf-8"))["sections"].values()).lower()
           for p in LABEL_DIR.glob("*.json")}
    SEARCH_FORMS = {"cyp3a4": ["cyp3a4", "cyp3a"], "p-gp": ["p-gp", "p-glycoprotein"],
                    "st. john's wort": ["st. john", "st john"]}

    def in_raw_text(drug, item):
        """在说明书原文里按整词搜索；返回包含该词的一小段原文。名称太短或是长短语时不搜。"""
        if len(item) < 4 or len(item.split()) > 3:
            return None
        for form in SEARCH_FORMS.get(item, [item]):
            m = re.search(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", raw.get(drug, ""))
            if m:
                t = raw[drug]
                return "…" + t[max(0, m.start() - 120): m.end() + 80] + "…"
        return None

    def find(drug, cat, item):
        """在说明书里找 item，返回（状态, 说明书原文）。"""
        entries = label[(drug, cat)]
        for e in entries:                              # ① 直接命中（target 或举例药名）
            if item == e["target"] or item in e["examples"]:
                neg = any(k in e["effect"] for k in NEGATIVE)
                return ("说明书不一致" if neg and cat == "ddi" else "说明书已收录"), e["evidence"]
        if cat == "ae":                                # ② 上位概念
            up = ancestors(item)
            if any(w in item for w in BLEED_WORDS):
                up.add("bleeding")
            for e in entries:
                if e["target"] in up:
                    return "上位概念收录", e["evidence"]
        if cat == "ddi":                               # ③ 类别：合用药属于说明书写的某个类别
            for keys, members in CLASS_MEMBERS.items():
                # 合用药本身是这个类别的成员，或文献写的就是类别名（如 "p-gp/cyp3a4 inhibitors"）
                if item in members or all(k in item for k in keys):
                    for e in entries:
                        if all(k in e["target"] for k in keys):
                            neg = any(k in e["effect"] for k in NEGATIVE)
                            return ("说明书不一致" if neg else "类别收录"), e["evidence"]
        snippet = in_raw_text(drug, item)               # ④ 兜底：说明书原文里有没有这个词
        if snippet:
            return "原文提及（抽取遗漏）", snippet
        return "仅文献报道", None

    # ---------- 文献图谱：每种药的报道项 ----------
    g = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    ntype = {nd["id"]: nd["type"] for nd in g["nodes"]}
    found = defaultdict(set)           # (药物, 类别, 项目) → PMID 集合
    for link in g["links"]:
        s, o = link["source"], link["target"]
        for r in link["relations"]:
            rel = r["relation"]
            if rel in AE_RELATIONS and s in DRUGS and ntype.get(o) == "adverse_event":
                found[(s, "ae", o)] |= set(r["pmids"])
            elif rel in DDI_RELATIONS and (s in DRUGS or o in DRUGS):
                drug, partner = (s, o) if s in DRUGS else (o, s)
                if ntype.get(partner) == "drug" and partner != drug:
                    found[(drug, "ddi", n(partner))] |= set(r["pmids"])
            elif rel in PK_RELATIONS and s in DRUGS:
                found[(s, "pk", n(o))] |= set(r["pmids"])

    rows = []
    for (drug, cat, item), pmids in sorted(found.items()):
        status, ev = find(drug, cat, item)
        rows.append({"drug": drug, "category": cat, "item": item, "n_papers": len(pmids),
                     "pmids": sorted(pmids)[:20], "status": status, "label_evidence": ev})

    # 反方向：说明书写了、文献没报道的
    covered = {(r["drug"], r["category"], r["item"]) for r in rows}
    label_only = []
    for (drug, cat), entries in label.items():
        seen = set()
        for e in entries:
            if e["target"] in seen:
                continue
            seen.add(e["target"])
            if not any((drug, cat, x) in covered for x in [e["target"], *e["examples"]]):
                label_only.append({"drug": drug, "category": cat, "item": e["target"], "effect": e["effect"]})

    OUT_JSON.write_text(json.dumps({"literature": rows, "label_only": label_only}, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    # ---------- 汇总报告 ----------
    CAT = {"ae": "不良反应", "ddi": "相互作用", "pk": "药代"}
    STATUSES = ["说明书已收录", "上位概念收录", "类别收录", "原文提及（抽取遗漏）", "说明书不一致", "仅文献报道"]
    lines = ["# 说明书交叉验证结果（自动生成）", "",
             f"文献图谱中与 7 种药相关的不良反应 / 相互作用 / 药代项目共 {len(rows)} 个；说明书信息 {len(facts)} 条。", "",
             "## 按类别", "", "| 类别 | " + " | ".join(STATUSES) + " | 合计 |", "|---|" + "---|" * (len(STATUSES) + 1)]
    for cat in CAT:
        rs = [r for r in rows if r["category"] == cat]
        lines.append(f"| {CAT[cat]} | " + " | ".join(str(sum(r["status"] == s for r in rs)) for s in STATUSES)
                     + f" | {len(rs)} |")
    multi = [r for r in rows if r["n_papers"] >= 2]
    lines += ["", f"只看至少 2 篇文献支持的项目（{len(multi)} 个）：", "",
              "| 类别 | " + " | ".join(STATUSES) + " |", "|---|" + "---|" * len(STATUSES)]
    for cat in CAT:
        rs = [r for r in multi if r["category"] == cat]
        lines.append(f"| {CAT[cat]} | " + " | ".join(str(sum(r["status"] == s for r in rs)) for s in STATUSES) + " |")

    lines += ["", "## 说明书不一致（文献报道了相互作用，说明书写无需调整 / 无相关作用）", "",
              "| 药物 | 合用药 | 文献数 | PMID | 说明书原文 |", "|---|---|---|---|---|"]
    for r in rows:
        if r["status"] == "说明书不一致":
            lines.append(f"| {r['drug']} | {r['item']} | {r['n_papers']} | {', '.join(map(str, r['pmids'][:5]))} | "
                         f"{r['label_evidence']} |")

    lines += ["", "## 仅文献报道（按文献数排序，潜在信号，需人工确认）", "",
              "| 药物 | 类别 | 项目 | 文献数 | PMID |", "|---|---|---|---|---|"]
    for r in sorted((r for r in rows if r["status"] == "仅文献报道"), key=lambda r: -r["n_papers"]):
        lines.append(f"| {r['drug']} | {CAT[r['category']]} | {r['item']} | {r['n_papers']} | "
                     f"{', '.join(map(str, r['pmids'][:5]))} |")

    lines += ["", f"## 说明书写了、文献图谱没有报道的（{len(label_only)} 项）", "",
              "| 药物 | 类别 | 项目 | 说明书描述 |", "|---|---|---|---|"]
    for r in sorted(label_only, key=lambda r: (r["drug"], r["category"])):
        lines.append(f"| {r['drug']} | {CAT[r['category']]} | {r['item']} | {r['effect']} |")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:20]))
    print(f"\n完整结果：{OUT_MD.relative_to(ROOT)}")


def review():
    """审核表：每行附文献证据句和说明书原文，由人工判断是不是真信号。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    from biolit.db import ACTIVE_VERSION, get_connection

    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    norm = Normalizer()
    conn = get_connection()
    rows = [r for r in data["literature"]
            if r["category"] in ("ddi", "pk") and r["status"] in ("说明书不一致", "仅文献报道")]
    rows.sort(key=lambda r: (r["status"] != "说明书不一致", -r["n_papers"], r["drug"], r["item"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "审核"
    ws.append(["药物", "类别", "合用药 / 酶", "文献数", "PMID", "比对结果", "文献证据句", "说明书原文",
               "你的判定（真信号 / 说明书其实有 / 抽取错误 / 不确定）", "备注"])
    CAT = {"ddi": "相互作用", "pk": "药代"}
    for r in rows:
        # 从数据库取这条关系的证据句：同一篇文献里，主体或客体分别是这个药和这个合用药 / 酶
        evs = []
        for pm in r["pmids"][:3]:
            for rel in conn.execute("SELECT subject, object, evidence FROM relations "
                                    "WHERE pmid = ? AND prompt_version = ?", (pm, ACTIVE_VERSION)):
                names = {(norm(rel["subject"]) or ""), (norm(rel["object"]) or "")}
                if r["drug"] in names and any(r["item"] in x or x in r["item"] for x in names if x):
                    evs.append(f"[PMID {pm}] {rel['evidence']}")
                    break
        ws.append([r["drug"], CAT[r["category"]], r["item"], r["n_papers"], ", ".join(map(str, r["pmids"][:5])),
                   r["status"], "\n".join(evs), r["label_evidence"] or "", "", ""])

    yellow = PatternFill("solid", fgColor="FFF2CC")
    for i, w in enumerate([11, 8, 22, 6, 18, 12, 70, 50, 18, 20], 1):
        ws.column_dimensions[chr(64 + i)].width = w
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        row[8].fill = yellow
    ws.freeze_panes = "A2"
    wb.save(REVIEW)
    print(f"已生成 {REVIEW.relative_to(ROOT)}：{len(rows)} 行")


if __name__ == "__main__":
    import sys
    review() if sys.argv[1:] == ["review"] else main()
