"""M4 可视化：把知识图谱生成一个可交互的网页（浏览器打开即可，可拖动、缩放、点击查看证据）。

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.graph.visualize                     # 只显示 ≥3 篇文献支持的关系
    python -m biolit.graph.visualize --min-papers 5      # 门槛调高，图更清爽
    python -m biolit.graph.visualize --focus apixaban    # 只看某个实体和它的直接邻居

输出：data/processed/graph.html（双击用浏览器打开）
"""
import argparse
import json
import math

from biolit.db import ROOT
from biolit.graph.build import load_graph

OUT_PATH = ROOT / "data" / "processed" / "graph.html"

# 节点颜色按实体类型；边颜色按关系类型
NODE_COLORS = {"drug": "#4C6EF5", "adverse_event": "#E8590C", "outcome": "#2F9E44",
               "enzyme": "#AE3EC9", "disease": "#868E96", "population": "#1098AD", "unknown": "#ADB5BD"}
EDGE_COLORS = {"increases_risk": "#E03131", "decreases_risk": "#2F9E44", "interacts_with": "#F08C00",
               "inhibits": "#7048E8", "induces": "#1C7ED6", "metabolized_by": "#AE3EC9",
               "contraindicated_in": "#212529"}
TYPE_ZH = {"drug": "药物", "adverse_event": "不良事件", "outcome": "临床结局", "enzyme": "酶 / 转运体",
           "disease": "疾病", "population": "人群", "unknown": "未知"}
REL_ZH = {"increases_risk": "增加风险", "decreases_risk": "降低风险", "interacts_with": "相互作用",
          "inhibits": "抑制", "induces": "诱导", "metabolized_by": "被代谢", "contraindicated_in": "禁用"}


def to_vis(G, min_papers: int, focus: str | None):
    """把 networkx 图转换成 vis-network 需要的 nodes / edges 列表。"""
    if focus:
        focus = focus.lower()
        if focus not in G:
            raise SystemExit(f"图谱里没有 '{focus}'，请检查拼写（需要用标准化后的名字，如 doac）")
        keep = {focus} | set(G.successors(focus)) | set(G.predecessors(focus))
        G = G.subgraph(keep)

    edges, used = [], set()
    for s, o, d in G.edges(data=True):
        for info in d["relations"]:
            if info["n_papers"] < min_papers:
                continue
            used.update((s, o))
            cmp = f" vs {info['comparator']}" if info["comparator"] else ""
            edges.append({
                "from": s, "to": o, "arrows": "to",
                "color": EDGE_COLORS.get(info["relation"], "#868E96"),
                "width": 1 + 2 * math.log(info["n_papers"]),
                "title": f"{REL_ZH.get(info['relation'], info['relation'])}{cmp}（{info['n_papers']} 篇）",
                # 以下字段给点击后的详情面板用
                "detail": {"subject": s, "object": o, "relation": REL_ZH.get(info["relation"], info["relation"]),
                           "comparator": info["comparator"], "n_papers": info["n_papers"],
                           "study_types": info["study_types"], "example": info["example"],
                           "pmids": info["pmids"][:20]},
            })

    nodes = [{
        "id": n, "label": n,
        "color": NODE_COLORS.get(G.nodes[n]["type"], "#ADB5BD"),
        "size": 8 + 3 * math.sqrt(G.nodes[n]["n_papers"]),
        "title": f"{n}（{TYPE_ZH.get(G.nodes[n]['type'], '')}，{G.nodes[n]['n_papers']} 篇文献）",
        "borderWidth": 3 if n == focus else 1,
    } for n in G.nodes if n in used]
    return nodes, edges


HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BioLit-KG 知识图谱</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js"
        onerror="this.onerror=null; this.src='https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js'"></script>
<style>
  body { margin: 0; font-family: system-ui, "Microsoft YaHei", sans-serif; display: flex; height: 100vh; color: #212529; }
  #graph { flex: 1; background: #fafafa; }
  #side { width: 340px; padding: 16px; overflow-y: auto; border-left: 1px solid #dee2e6; font-size: 14px; background: #fff; }
  h1 { font-size: 18px; margin: 0 0 4px; } .muted { color: #868e96; font-size: 12px; }
  .legend span { display: inline-block; margin: 2px 8px 2px 0; } .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 4px; vertical-align: middle; }
  .line { width: 16px; height: 3px; display: inline-block; margin-right: 4px; vertical-align: middle; }
  input { width: 100%; padding: 6px; box-sizing: border-box; margin: 8px 0; }
  blockquote { margin: 8px 0; padding: 8px; background: #f1f3f5; border-left: 3px solid #adb5bd; }
  a { color: #1c7ed6; }
</style></head>
<body>
<div id="graph"></div>
<div id="side">
  <h1>BioLit-KG 知识图谱</h1>
  <div class="muted">__SUMMARY__</div>
  <input id="search" placeholder="搜索实体，如 apixaban，回车定位">
  <div class="legend"><b>节点</b><br>__NODE_LEGEND__</div>
  <div class="legend" style="margin-top:8px"><b>关系</b><br>__EDGE_LEGEND__</div>
  <hr><div id="detail" class="muted">点击一条连线，查看证据和原文链接。</div>
</div>
<script>
const nodes = new vis.DataSet(__NODES__);
const edges = new vis.DataSet(__EDGES__);
const network = new vis.Network(document.getElementById("graph"), {nodes, edges}, {
  physics: { solver: "forceAtlas2Based", stabilization: { iterations: 200 } },
  nodes: { shape: "dot", font: { size: 22, strokeWidth: 4, strokeColor: "#fafafa" } },
  edges: { smooth: { type: "dynamic" } },
  interaction: { hover: true, tooltipDelay: 150 },
});
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
network.on("click", params => {
  if (!params.edges.length || params.nodes.length) return;
  const d = edges.get(params.edges[0]).detail;
  const types = Object.entries(d.study_types).map(([k, v]) => `${esc(k)} ${v}`).join("、");
  const links = d.pmids.map(p => `<a href="https://pubmed.ncbi.nlm.nih.gov/${p}/" target="_blank">${p}</a>`).join(" ");
  document.getElementById("detail").innerHTML = `
    <div style="color:#212529"><b>${esc(d.subject)}</b> → ${esc(d.relation)} → <b>${esc(d.object)}</b></div>
    ${d.comparator ? `<div>对照：${esc(d.comparator)}</div>` : ""}
    <div>支持文献：${d.n_papers} 篇（${types}）</div>
    <blockquote>${esc(d.example.text)}<br><span class="muted">— PMID ${d.example.pmid}</span></blockquote>
    <div>文献：${links}</div>`;
});
document.getElementById("search").addEventListener("keydown", e => {
  if (e.key !== "Enter") return;
  const q = e.target.value.trim().toLowerCase();
  const hit = nodes.get().find(n => n.id === q) || nodes.get().find(n => n.id.includes(q));
  if (hit) { network.selectNodes([hit.id]); network.focus(hit.id, { scale: 1.5, animation: true }); }
});
</script></body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-papers", type=int, default=3, help="关系至少要有几篇文献支持才显示")
    parser.add_argument("--focus", default=None, help="只显示某个实体及其直接邻居")
    args = parser.parse_args()

    nodes, edges = to_vis(load_graph(), args.min_papers, args.focus)
    node_legend = "".join(f'<span><i class="dot" style="background:{c}"></i>{TYPE_ZH[t]}</span>'
                          for t, c in NODE_COLORS.items() if t != "unknown")
    edge_legend = "".join(f'<span><i class="line" style="background:{c}"></i>{REL_ZH[r]}</span>'
                          for r, c in EDGE_COLORS.items())
    summary = (f"{len(nodes)} 个实体 · {len(edges)} 条关系 · 门槛 ≥{args.min_papers} 篇"
               + (f" · 聚焦 {args.focus}" if args.focus else ""))
    html = (HTML.replace("__NODES__", json.dumps(nodes, ensure_ascii=False))
                .replace("__EDGES__", json.dumps(edges, ensure_ascii=False))
                .replace("__NODE_LEGEND__", node_legend).replace("__EDGE_LEGEND__", edge_legend)
                .replace("__SUMMARY__", summary))
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"{summary}\n已生成：{OUT_PATH.relative_to(ROOT)}（用浏览器打开）")


if __name__ == "__main__":
    main()
