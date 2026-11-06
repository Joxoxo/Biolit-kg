// 以一个药为中心的小网络图：只画一跳邻居（酶、转运体、合用药），颜色表示说明书比对结果
import { useEffect, useRef } from "react";
import type { Mechanism } from "@/lib/api";
import { mechStatus } from "@/sections/status";

type VisModule = typeof import("vis-network/standalone");
type Net = InstanceType<VisModule["Network"]>;

interface Props {
  drug: string;
  drugLabel: string;
  items: Mechanism[];
  selected: string | null;
  onSelect: (partner: string | null) => void;
}

export default function EgoGraph({ drug, drugLabel, items, selected, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const net = useRef<Net | null>(null);

  useEffect(() => {
    if (!box.current) return;
    let destroyed = false;
    import("vis-network/standalone").then((vis) => {
      if (destroyed || !box.current) return;
      const nodes = [
        { id: drug, label: drugLabel, shape: "box", color: { background: "#0a0a0a", border: "#0a0a0a" },
          font: { color: "#ffffff", size: 16, face: "Noto Sans SC" }, margin: { top: 8, bottom: 8, left: 10, right: 10 } },
        ...items.map((m) => {
          const st = mechStatus(m);
          return {
            id: m.partner,
            label: m.partner,
            shape: m.partner_type === "enzyme" ? "triangle" : "dot",
            size: 8 + 3 * Math.sqrt(m.n_papers),
            color: { background: st.color, border: st.color },
            font: { size: 13, face: "JetBrains Mono", strokeWidth: 4, strokeColor: "#ffffff" },
            title: `${m.partner}（${m.n_papers} 篇）· ${st.label}`,
          };
        }),
      ];
      const edges = items.map((m) => ({
        id: m.partner,
        from: m.direction === "out" ? drug : m.partner,
        to: m.direction === "out" ? m.partner : drug,
        arrows: "to",
        color: { color: "rgba(10,10,10,0.25)", highlight: "#fe5000" },
        width: 1 + Math.log(m.n_papers + 1),
      }));
      net.current = new vis.Network(box.current, { nodes, edges }, {
        physics: { solver: "forceAtlas2Based", stabilization: { iterations: 150 } },
        interaction: { hover: true, tooltipDelay: 120 },
      });
      net.current.on("click", (p: { nodes: string[] }) => {
        const id = p.nodes[0];
        onSelect(id && id !== drug ? id : null);
      });
    });
    return () => {
      destroyed = true;
      net.current?.destroy();
      net.current = null;
    };
    // onSelect 每次渲染都会变，但不需要因此重画网络
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drug, drugLabel, items]);

  // 列表里选中某一项时，图上同步高亮
  useEffect(() => {
    if (!net.current) return;
    if (selected) net.current.selectNodes([selected]);
    else net.current.unselectAll();
  }, [selected]);

  return <div ref={box} className="absolute inset-0" />;
}
