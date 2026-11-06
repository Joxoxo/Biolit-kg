"""药物安全档案：把一个药在图谱里的所有关系，整理成网页"药物安全档案"页需要的格式。

两部分：
1. 疗效与安全性比较：（对照药, 结局）→ 降低几篇、增加几篇、研究类型分布，以及结论是否一致
   "华法林相比阿哌沙班增加大出血"会换成阿哌沙班的视角，记作"阿哌沙班相比华法林降低大出血"，两者合并计数
2. 相互作用与代谢：合用药 / 酶 / 转运体，附说明书比对结果和人工审核判定

结论是否一致（最简单的矛盾检测）：
- 少数方向的文献 ≥ 2 篇 → 不一致（mixed）
- 只有 1 篇相反 → 仍按多数方向，但标出"1 篇相反"
"""
import json
from collections import defaultdict
from functools import lru_cache

from biolit.db import ROOT
from biolit.graph.build import GRAPH_PATH

CROSSCHECK = ROOT / "data" / "processed" / "label_crosscheck.json"

DRUGS = {"apixaban": "阿哌沙班", "rivaroxaban": "利伐沙班", "dabigatran": "达比加群", "edoxaban": "依度沙班",
         "warfarin": "华法林", "clopidogrel": "氯吡格雷", "ticagrelor": "替格瑞洛"}
EFFECT_RELATIONS = {"decreases_risk", "increases_risk"}
FLIP = {"decreases_risk": "increases_risk", "increases_risk": "decreases_risk"}
MECH_RELATIONS = {"interacts_with", "inhibits", "induces", "metabolized_by", "transported_by"}
STUDY_ORDER = ["meta_analysis", "rct", "observational", "clinical_pk", "review", "case_report", "preclinical", "other"]


@lru_cache(maxsize=1)
def _load():
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    cross = json.loads(CROSSCHECK.read_text(encoding="utf-8")) if CROSSCHECK.exists() else {"literature": []}
    return graph, cross


def build_profile(drug: str) -> dict:
    graph, cross = _load()
    ntype = {n["id"]: n["type"] for n in graph["nodes"]}

    # ---------- ① 比较 ----------
    comp = defaultdict(lambda: {"dec": set(), "inc": set(), "study_types": defaultdict(int), "example": None})
    for link in graph["links"]:
        s, o = link["source"], link["target"]
        for r in link["relations"]:
            if r["relation"] not in EFFECT_RELATIONS:
                continue
            if s == drug:
                rel, comparator = r["relation"], r["comparator"] or ""
            elif r["comparator"] == drug:                 # 换成本药的视角：方向取反，对照药换成原来的主体
                rel, comparator = FLIP[r["relation"]], s
            else:
                continue
            c = comp[(comparator, o)]
            c["dec" if rel == "decreases_risk" else "inc"].update(r["pmids"])
            for k, v in r["study_types"].items():
                c["study_types"][k] += v
            if r.get("example") and (c["example"] is None or s == drug):
                c["example"] = r["example"]

    comparisons = []
    for (comparator, outcome), c in comp.items():
        n_dec, n_inc = len(c["dec"]), len(c["inc"])
        minority = min(n_dec, n_inc)
        direction = "mixed" if minority >= 2 else ("decreases" if n_dec >= n_inc else "increases")
        comparisons.append({
            "comparator": comparator, "outcome": outcome, "outcome_type": ntype.get(outcome, "unknown"),
            "direction": direction, "n_dec": n_dec, "n_inc": n_inc,
            "n_papers": len(c["dec"] | c["inc"]), "pmids": sorted(c["dec"] | c["inc"]),
            "study_types": {k: c["study_types"][k] for k in STUDY_ORDER if c["study_types"].get(k)},
            "example": c["example"],
        })
    comparisons.sort(key=lambda x: (-x["n_papers"], x["outcome"]))

    # ---------- ② 相互作用与代谢 ----------
    label = {}
    for row in cross["literature"]:
        if row["drug"] == drug and row["category"] in ("ddi", "pk"):
            label[row["item"]] = row
    mech = defaultdict(lambda: {"relations": set(), "pmids": set(), "example": None, "direction": ""})
    for link in graph["links"]:
        s, o = link["source"], link["target"]
        if drug not in (s, o):
            continue
        partner = o if s == drug else s
        for r in link["relations"]:
            if r["relation"] not in MECH_RELATIONS:
                continue
            m = mech[partner]
            m["relations"].add(r["relation"])
            m["pmids"].update(r["pmids"])
            m["example"] = m["example"] or r.get("example")
            # 记下方向：本药"被代谢 / 被抑制"还是"去抑制别人"，网页上的箭头会用到
            m["direction"] = m["direction"] or ("out" if s == drug else "in")
    mechanisms = []
    for partner, m in mech.items():
        row = label.get(partner) or label.get(partner.replace("rifampicin", "rifampin"))
        mechanisms.append({
            "partner": partner, "partner_type": ntype.get(partner, "unknown"),
            "relations": sorted(m["relations"]), "direction": m["direction"],
            "n_papers": len(m["pmids"]), "pmids": sorted(m["pmids"]), "example": m["example"],
            "label_status": row["status"] if row else None,
            "label_evidence": row.get("label_evidence") if row else None,
            "review": row.get("review") if row else None,          # 人工审核判定（如果审核过）
            "review_note": row.get("review_note") if row else None,
        })
    mechanisms.sort(key=lambda x: (-x["n_papers"], x["partner"]))

    all_pmids = {p for c in comparisons for p in c["pmids"]} | {p for m in mechanisms for p in m["pmids"]}
    return {
        "drug": drug, "drug_zh": DRUGS.get(drug, drug),
        "n_papers": len(all_pmids),
        "n_comparisons": len(comparisons),
        "n_conflicts": sum(c["direction"] == "mixed" for c in comparisons),
        "n_signals": sum(m["review"] == "真信号" for m in mechanisms),
        "comparisons": comparisons,
        "mechanisms": mechanisms,
    }
