import { useEffect, useRef, useState } from "react";
import { getGraph, type GraphData } from "@/lib/api";

type VisNetworkModule = typeof import("vis-network/standalone");
type NetworkInstance = InstanceType<VisNetworkModule["Network"]>;

// Minimal vis-network types to avoid `any`
interface VisNode {
  id: string;
  label: string;
  color: string;
  shape: string;
  size: number;
  title: string;
}

interface RelationDetail {
  subject: string;
  object: string;
  relation: string;
  comparator: string | null;
  n_papers: number;
  study_types: Record<string, number>;
  pmids: number[];
  example: { pmid: number; text: string } | null;
}

interface VisEdge {
  from: string;
  to: string;
  arrows: string;
  color: string;
  width: number;
  title: string;
  detail: RelationDetail;
}

// 只展示药物与酶/转运体之间的作用关系（机制类），不展示临床风险结论
const VISIBLE_RELATIONS = new Set([
  "interacts_with",
  "inhibits",
  "induces",
  "metabolized_by",
  "transported_by",
]);

const NODE_COLORS: Record<string, string> = {
  drug: "#4C6EF5",
  enzyme: "#AE3EC9",
  unknown: "#ADB5BD",
};

const NODE_SHAPES: Record<string, string> = {
  drug: "dot",
  enzyme: "triangle",
};

const EDGE_COLORS: Record<string, string> = {
  interacts_with: "#F08C00",
  inhibits: "#7048E8",
  induces: "#1C7ED6",
  metabolized_by: "#AE3EC9",
  transported_by: "#0CA678",
};

const REL_ZH: Record<string, string> = {
  increases_risk: "增加风险",
  decreases_risk: "降低风险",
  interacts_with: "相互作用",
  inhibits: "抑制",
  induces: "诱导",
  metabolized_by: "被代谢",
  transported_by: "被转运",
  contraindicated_in: "禁用",
};

const TYPE_ZH: Record<string, string> = {
  drug: "药物",
  adverse_event: "不良事件",
  outcome: "临床结局",
  enzyme: "酶 / 转运体",
  disease: "疾病",
  population: "人群",
  unknown: "未知",
};

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<unknown>(null);
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minPapers, setMinPapers] = useState(3);
  const [focus, setFocus] = useState("");
  const [detail, setDetail] = useState<React.ReactNode>(null);

  useEffect(() => {
    getGraph()
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!data || !containerRef.current) return;
    const container = containerRef.current;

    let destroyed = false;
    let net: NetworkInstance | null = null;

    import("vis-network/standalone").then((vis) => {
      if (destroyed) return;

      const nodesRaw: VisNode[] = data.nodes.map((n) => ({
        id: n.id,
        label: n.id,
        color: NODE_COLORS[n.type] || NODE_COLORS.unknown,
        shape: NODE_SHAPES[n.type] || "dot",
        size: 8 + 3 * Math.sqrt(n.n_papers),
        title: `${n.id}（${TYPE_ZH[n.type] || n.type}，${n.n_papers} 篇文献）`,
      }));

      const edgesRaw: VisEdge[] = [];
      const usedNodes = new Set<string>();
      data.links.forEach((link) => {
        link.relations.forEach((r) => {
          if (r.n_papers < minPapers) return;
          if (!VISIBLE_RELATIONS.has(r.relation)) return;
          usedNodes.add(link.source);
          usedNodes.add(link.target);
          const cmp = r.comparator ? ` vs ${r.comparator}` : "";
          edgesRaw.push({
            from: link.source,
            to: link.target,
            arrows: "to",
            color: EDGE_COLORS[r.relation] || "#868E96",
            width: 1 + 2 * Math.log(r.n_papers),
            title: `${REL_ZH[r.relation] || r.relation}${cmp}（${r.n_papers} 篇）`,
            detail: { ...r, subject: link.source, object: link.target },
          });
        });
      });

      const nodes = nodesRaw.filter((n) => usedNodes.has(n.id));

      if (focus.trim()) {
        const q = focus.trim().toLowerCase();
        const center = nodes.find((n) => n.id.toLowerCase() === q)?.id;
        if (center) {
          const connected = new Set<string>([center]);
          edgesRaw.forEach((e) => {
            if (e.from === center) connected.add(e.to);
            if (e.to === center) connected.add(e.from);
          });
          const nodeSet = new Set(connected);
          net = new vis.Network(container, {
            nodes: nodes.filter((n) => nodeSet.has(n.id)),
            edges: edgesRaw.filter((e) => nodeSet.has(e.from) && nodeSet.has(e.to)),
          }, {
            physics: { solver: "forceAtlas2Based", stabilization: { iterations: 200 } },
            nodes: { shape: "dot", font: { size: 24, strokeWidth: 5, strokeColor: "#fafafa" } },
            edges: { smooth: { enabled: true, type: "dynamic", roundness: 0.5 } },
            interaction: { hover: true, tooltipDelay: 150 },
          });
        }
      }

      if (!net) {
        net = new vis.Network(container, { nodes, edges: edgesRaw }, {
          physics: { solver: "forceAtlas2Based", stabilization: { iterations: 200 } },
          nodes: { shape: "dot", font: { size: 24, strokeWidth: 5, strokeColor: "#fafafa" } },
          edges: { smooth: { enabled: true, type: "dynamic", roundness: 0.5 } },
          interaction: { hover: true, tooltipDelay: 150 },
        });
      }

      net.on("click", (params: { edges: string[]; nodes: string[] }) => {
        if (!net) return;
        if (!params.edges.length || params.nodes.length) {
          setDetail(null);
          return;
        }
        const dataSet = (net as unknown as { body: { data: { edges: { get: (id: string) => { detail: RelationDetail } | null } } } }).body.data.edges;
        const edge = dataSet.get(params.edges[0]);
        if (!edge) return;
        const d = edge.detail;
        const types = Object.entries(d.study_types)
          .map(([k, v]) => `${TYPE_ZH[k] || k} ${v}`)
          .join("、");
        const links = d.pmids.slice(0, 20).map((p: number) => (
          <a
            key={p}
            href={`https://pubmed.ncbi.nlm.nih.gov/${p}/`}
            target="_blank"
            rel="noreferrer"
            className="mono text-[11px] text-[var(--pv-accent)] hover:underline mr-2"
          >
            {p}
          </a>
        ));
        setDetail(
          <div className="space-y-2 text-[13px]">
            <div className="font-bold">
              {d.subject} → {REL_ZH[d.relation] || d.relation} → {d.object}
            </div>
            {d.comparator && <div className="text-black/60">对照：{d.comparator}</div>}
            <div className="text-black/60">支持文献：{d.n_papers} 篇（{types}）</div>
            {d.example && (
              <blockquote className="pv-border-l-2 border-l-[3px] border-[var(--pv-accent)] pl-3 py-1 text-black/70 italic leading-relaxed">
                {d.example.text}
                <span className="block text-black/40 mt-1 not-italic">— PMID {d.example.pmid}</span>
              </blockquote>
            )}
            <div>{links}</div>
          </div>
        );
      });

      networkRef.current = net;
    });

    return () => {
      destroyed = true;
      const n = networkRef.current as NetworkInstance | null;
      if (n && typeof n.destroy === "function") {
        n.destroy();
      }
      networkRef.current = null;
    };
  }, [data, minPapers, focus]);

  if (loading) return <PageMessage>加载知识图谱…</PageMessage>;
  if (error) return <PageMessage tone="bad">加载失败：{error}</PageMessage>;

  return (
    <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
      <div className="flex-1 min-h-0 relative bg-[#fafafa]">
        <div ref={containerRef} className="absolute inset-0" />
      </div>

      <aside className="lg:w-[360px] shrink-0 pv-border-l bg-white overflow-y-auto pv-scroll p-4 space-y-4">
        <div>
          <div className="pv-label mb-2">聚焦实体 · Focus</div>
          <div className="flex gap-2">
            <input
              type="text"
              value={focus}
              onChange={(e) => setFocus(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && setFocus(focus)}
              placeholder="如 apixaban"
              className="flex-1 mono text-[13px] px-3 py-2 pv-border bg-white focus:outline-none focus:ring-2 focus:ring-[var(--pv-accent)]"
            />
            <button
              type="button"
              onClick={() => setFocus("")}
              className="pv-chip"
            >
              重置
            </button>
          </div>
        </div>

        <div>
          <div className="pv-label mb-2">最小文献数 · Min Papers（{minPapers}）</div>
          <input
            type="range"
            min={1}
            max={10}
            step={1}
            value={minPapers}
            onChange={(e) => setMinPapers(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div>
          <div className="pv-label mb-2">节点图例 · Nodes</div>
          <div className="flex flex-wrap gap-3 text-[11px]">
            {(["drug", "enzyme"] as const).map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <span
                  className={NODE_SHAPES[t] === "triangle" ? "w-2.5 h-2.5" : "w-2.5 h-2.5 rounded-full"}
                  style={
                    NODE_SHAPES[t] === "triangle"
                      ? { background: NODE_COLORS[t], clipPath: "polygon(50% 0, 100% 100%, 0 100%)" }
                      : { background: NODE_COLORS[t] }
                  }
                />
                {TYPE_ZH[t]}
              </span>
            ))}
          </div>
        </div>

        <div>
          <div className="pv-label mb-2">关系图例 · Edges</div>
          <div className="flex flex-wrap gap-2 text-[11px]">
            {[...VISIBLE_RELATIONS].map((r) => (
              <span key={r} className="flex items-center gap-1">
                <span className="w-3 h-[3px]" style={{ background: EDGE_COLORS[r] }} />
                {REL_ZH[r] || r}
              </span>
            ))}
          </div>
        </div>

        <div className="pv-border p-3 bg-black/[0.02]">
          <div className="pv-label mb-2">关系详情 · Detail</div>
          {detail || <div className="text-[12.5px] text-black/50">点击一条连线查看证据与 PMID。</div>}
        </div>
      </aside>
    </div>
  );
}

function PageMessage({ children, tone }: { children: React.ReactNode; tone?: "bad" }) {
  return (
    <div className={`flex-1 flex items-center justify-center text-[14px] ${tone ? "text-[var(--pv-bad)]" : "text-black/60"}`}>
      {children}
    </div>
  );
}
