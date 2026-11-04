import { useMemo, useState } from "react";
import type { Relation } from "@/types/pv";
import { normDrug } from "@/sections/ComparisonView";

const GRID =
  "grid grid-cols-[2.2rem_minmax(90px,1fr)_5.5rem_minmax(110px,1.2fr)_minmax(80px,0.8fr)_minmax(120px,1.2fr)_6.5rem] gap-x-3 px-3";

export function RelationTable({
  relations,
  selected,
  onSelect,
  papers,
}: {
  relations: Relation[];
  selected: Relation | null;
  onSelect: (r: Relation) => void;
  papers: Record<string, string>;
}) {
  // 按主体药物分组，默认全部折叠，避免一次性铺出全部关系
  const groups = useMemo(() => {
    const m = new Map<string, { label: string; items: { r: Relation; idx: number }[] }>();
    relations.forEach((r, idx) => {
      const k = normDrug(r.subject) || "(未标注)";
      if (!m.has(k)) m.set(k, { label: r.subject, items: [] });
      m.get(k)!.items.push({ r, idx });
    });
    return [...m.entries()].sort((a, b) => b[1].items.length - a[1].items.length);
  }, [relations]);

  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());
  const toggle = (k: string) => {
    const next = new Set(openGroups);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setOpenGroups(next);
  };

  return (
    <div className="flex-1 min-w-0 min-h-0 flex flex-col">
      {/* table head */}
      <div className={`${GRID} pv-border-b bg-white`} role="row">
        {["#", "主体", "关系", "客体", "对照药", "效果 / 效应量", "PMID"].map((h, i) => (
          <div key={i} className="pv-label py-2.5 truncate" role="columnheader">
            {h}
          </div>
        ))}
      </div>

      <div className="pv-rows flex-1 overflow-y-auto pv-scroll">
        {groups.map(([key, g]) => {
          const open = openGroups.has(key);
          return (
            <div key={key}>
              {/* group header */}
              <button
                type="button"
                onClick={() => toggle(key)}
                aria-expanded={open}
                className="w-full flex items-center gap-3 px-3 py-3 text-left pv-border-b bg-black/[0.03] hover:bg-black/[0.06] transition-colors cursor-pointer sticky top-0"
              >
                <span className="mono text-[12px] text-black/40 w-4">{open ? "−" : "+"}</span>
                <span className="mono font-bold text-[13px] truncate">{g.label}</span>
                <span className="mono text-[11px] text-black/45 ml-auto shrink-0">{g.items.length} 条关系</span>
              </button>

              {open &&
                g.items.map(({ r, idx }) => (
                  <RelationRow
                    key={`${r.pmid}-${idx}`}
                    r={r}
                    n={idx + 1}
                    isSel={selected === r}
                    onSelect={onSelect}
                    papers={papers}
                  />
                ))}
            </div>
          );
        })}

        {relations.length === 0 && (
          <div className="m-6 pv-border border-dashed p-10 text-center">
            <div className="pv-label mb-2">Empty Result</div>
            <div className="text-[13px] text-black/60">当前筛选条件下没有匹配的关系，请调整筛选器。</div>
          </div>
        )}
      </div>
    </div>
  );
}

function RelationRow({
  r, n, isSel, onSelect, papers,
}: {
  r: Relation;
  n: number;
  isSel: boolean;
  onSelect: (r: Relation) => void;
  papers: Record<string, string>;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(r)}
      aria-pressed={isSel}
      aria-label={`${r.subject} ${r.relation} ${r.object}`}
      className={`pv-row ${GRID} w-full text-left items-center pv-border-b relative ${isSel ? "bg-[var(--pv-accent-soft)]" : "bg-white"}`}
    >
      <span
        className={`absolute left-0 top-0 bottom-0 w-[3px] ${isSel ? "bg-[var(--pv-accent)]" : "bg-transparent"}`}
        aria-hidden="true"
      />
      <span className="mono text-[11px] text-black/45 py-2.5">{String(n).padStart(3, "0")}</span>
      <span className="mono text-[12.5px] font-bold truncate py-2.5" title={r.subject}>
        {r.subject}
      </span>
      <span className="text-[12px] py-2.5 whitespace-nowrap">{r.relation}</span>
      <span className="text-[12px] truncate py-2.5" title={r.object}>
        {r.object}
      </span>
      <span className="mono text-[11.5px] text-black/60 truncate py-2.5" title={r.comparator || undefined}>
        {r.comparator || "—"}
      </span>
      <span className="mono text-[11.5px] py-2.5 min-w-0">
        <span className="marquee-mask block w-full">
          <span className="marquee-track marquee-anim">
            <span className="inline-block pr-10">{r.effect || "—"}</span>
            <span className="inline-block pr-10" aria-hidden="true">{r.effect || "—"}</span>
          </span>
        </span>
      </span>
      <span className="mono text-[11px] text-black/55 py-2.5 truncate" title={papers[r.pmid]}>
        {r.pmid}
      </span>
    </button>
  );
}

export function useFiltered(relations: Relation[], f: {
  q: string; relations: Set<string>; onlyWithEff: boolean;
}) {
  return useMemo(() => {
    const q = f.q.trim().toLowerCase();
    return relations.filter((r) => {
      if (f.relations.size > 0 && !f.relations.has(r.relation)) return false;
      if (f.onlyWithEff && !r.eff) return false;
      if (q) {
        const hay = `${r.subject} ${r.object} ${r.comparator} ${r.population} ${r.pmid}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [relations, f]);
}
