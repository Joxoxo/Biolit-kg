"""M4 知识图谱：把关系表变成一张"网"。

- 节点（node）= 标准化后的实体，如 apixaban、major bleeding
- 边（edge）  = 关系，如 apixaban --decreases_risk--> major bleeding

同一条关系可能被很多篇文献报道，所以把它们合并，并记录：
支持文献数、PMID 列表、研究类型分布、一条示例证据。

注意：对照药是关系的一部分，不能丢。
例如利伐沙班"相比阿哌沙班"出血更多，但"相比华法林"出血更少 ——
如果不区分对照药，这两条结论会混在一起、互相矛盾。
所以合并的依据是 (主体, 关系, 客体, 对照药) 四者都相同。
支持文献越多、证据等级越高，这条关系越可信。

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.graph.build
"""
import json
from collections import Counter, defaultdict

import networkx as nx

from biolit.db import ACTIVE_VERSION, ROOT, get_connection

GRAPH_PATH = ROOT / "data" / "processed" / "graph.json"

# 研究类型的证据等级（数字越大越强），用来给每条边打一个"证据分"
EVIDENCE_LEVEL = {"meta_analysis": 5, "rct": 4, "observational": 3, "clinical_pk": 3,
                  "case_report": 2, "review": 1, "preclinical": 1, "other": 1}


def build_graph(conn, include_unverified: bool = False) -> nx.DiGraph:
    # 1. 节点类型：同一个实体在不同文献里可能被标成不同类型，取出现最多的那个
    type_votes = defaultdict(Counter)
    for row in conn.execute("SELECT name_norm, type FROM entities WHERE name_norm IS NOT NULL "
                            "AND prompt_version = ?", (ACTIVE_VERSION,)):
        type_votes[row["name_norm"]][row["type"]] += 1

    # 2. 取关系，并带上所在文献的研究类型
    sql = """SELECT r.pmid, r.subject_norm AS s, r.relation AS rel, r.object_norm AS o,
                    r.comparator_norm AS cmp, r.evidence, r.evidence_status, e.study_type
             FROM relations r
             JOIN extractions e ON e.pmid = r.pmid AND e.prompt_version = r.prompt_version
                               AND e.model = r.model AND e.status = 'ok'
             WHERE r.subject_norm IS NOT NULL AND r.object_norm IS NOT NULL
               AND r.prompt_version = ?"""
    if not include_unverified:
        sql += " AND r.evidence_status != 'unverified'"   # 证据找不到原文的，默认不进图谱

    # 3. 按 (主体, 关系, 客体, 对照药) 合并
    edges = defaultdict(lambda: {"pmids": set(), "study_types": Counter(), "evidence": None})
    for r in conn.execute(sql, (ACTIVE_VERSION,)):
        e = edges[(r["s"], r["rel"], r["o"], r["cmp"])]
        if r["pmid"] in e["pmids"]:
            continue                                     # 同一篇文献重复报道同一关系，只算一次
        e["pmids"].add(r["pmid"])
        e["study_types"][r["study_type"]] += 1
        if e["evidence"] is None:
            e["evidence"] = {"pmid": r["pmid"], "text": r["evidence"]}

    # 4. 组装成 networkx 图
    #    DiGraph = 有向图（关系有方向）
    #    两个节点之间可能有多条关系（不同关系类型、不同对照药），都存在边的 relations 列表里
    G = nx.DiGraph()
    for (s, rel, o, cmp), e in edges.items():
        for node in (s, o):
            if node not in G:
                votes = type_votes.get(node)
                G.add_node(node, type=votes.most_common(1)[0][0] if votes else "unknown")
        score = sum(EVIDENCE_LEVEL.get(t, 1) * n for t, n in e["study_types"].items())
        info = {
            "relation": rel,
            "comparator": cmp,
            "n_papers": len(e["pmids"]),
            "pmids": sorted(e["pmids"]),
            "study_types": dict(e["study_types"]),
            "evidence_score": score,
            "example": e["evidence"],
        }
        if not G.has_edge(s, o):
            G.add_edge(s, o, relations=[])
        G[s][o]["relations"].append(info)

    # 5. 每个节点被多少篇文献提到（作为节点大小）
    for node in G:
        pmids = set()
        for _, _, d in list(G.out_edges(node, data=True)) + list(G.in_edges(node, data=True)):
            for info in d["relations"]:
                pmids.update(info["pmids"])
        G.nodes[node]["n_papers"] = len(pmids)
    return G


def save_graph(G: nx.DiGraph, path=GRAPH_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nx.node_link_data(G, edges="links"), ensure_ascii=False), encoding="utf-8")


def load_graph(path=GRAPH_PATH) -> nx.DiGraph:
    return nx.node_link_graph(json.loads(path.read_text(encoding="utf-8")), edges="links")


def main():
    conn = get_connection()
    G = build_graph(conn)
    save_graph(G)

    n_rel = sum(len(d["relations"]) for _, _, d in G.edges(data=True))
    print(f"知识图谱：{G.number_of_nodes()} 个节点，{G.number_of_edges()} 对相连的节点，共 {n_rel} 条关系")
    print("节点类型：", dict(Counter(t for _, t in G.nodes(data="type")).most_common()))

    # PageRank：衡量节点在网络中的"重要性"（被越多重要节点连接，分数越高）
    pr = nx.pagerank(G.to_undirected())
    print("\n最核心的 10 个实体（PageRank）：")
    for node, score in sorted(pr.items(), key=lambda x: -x[1])[:10]:
        print(f"  {node:<32} {G.nodes[node]['type']:<14} 文献 {G.nodes[node]['n_papers']:>3} 篇  分数 {score:.3f}")

    print("\n文献支持最多的 12 条关系：")
    flat = [(s, o, info) for s, o, d in G.edges(data=True) for info in d["relations"]]
    for s, o, info in sorted(flat, key=lambda x: -x[2]["n_papers"])[:12]:
        cmp = f"（对照：{info['comparator']}）" if info["comparator"] else ""
        print(f"  {s} --{info['relation']}--> {o}{cmp}  [{info['n_papers']} 篇]")

    print(f"\n图谱已保存到 {GRAPH_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
