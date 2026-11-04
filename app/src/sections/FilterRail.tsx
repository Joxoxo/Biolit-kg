import { useMemo } from "react";
import type { Relation, FilterState } from "@/types/pv";

const RELATION_TYPES = ["降低风险", "增加风险", "相互作用", "抑制", "被代谢", "诱导", "禁用"];

export function FilterRail({
  all,
  filter,
  onChange,
  onReset,
}: {
  all: Relation[];
  filter: FilterState;
  onChange: (f: FilterState) => void;
  onReset: () => void;
}) {
  const relCounts = useMemo(() => countBy(all, (r) => r.relation), [all]);

  const toggle = (set: Set<string>, key: string, has: boolean) => {
    const next = new Set(set);
    if (has) next.delete(key);
    else next.add(key);
    return next;
  };

  return (
    <aside className="pv-border-r bg-white flex flex-col shrink-0 w-full lg:w-[264px] lg:overflow-y-auto lg:h-full pv-scroll">
      <div className="p-4 space-y-6">
        {/* search */}
        <div>
          <div className="pv-label mb-2">检索 · Search</div>
          <input
            type="search"
            value={filter.q}
            onChange={(e) => onChange({ ...filter, q: e.target.value })}
            placeholder="药物 / 客体 / 人群…"
            aria-label="检索药物、客体或人群"
            className="w-full mono text-[13px] px-3 py-2 pv-border bg-white placeholder:text-black/35 focus:outline-none focus:ring-2 focus:ring-[var(--pv-accent)]"
          />
        </div>

        {/* relation type */}
        <div>
          <div className="pv-label mb-2">关系类型 · Relation</div>
          <div className="flex flex-wrap gap-1.5">
            {RELATION_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                className="pv-chip"
                aria-pressed={filter.relations.has(t)}
                onClick={() => onChange({ ...filter, relations: toggle(filter.relations, t, filter.relations.has(t)) })}
              >
                {t}
                <span className="opacity-55 ml-1">{relCounts[t] ?? 0}</span>
              </button>
            ))}
          </div>
        </div>

        {/* effect size switch */}
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <button
            type="button"
            role="switch"
            aria-checked={filter.onlyWithEff}
            aria-label="仅显示含效应量的关系"
            onClick={() => onChange({ ...filter, onlyWithEff: !filter.onlyWithEff })}
            className={`relative w-9 h-5 pv-border transition-colors ${filter.onlyWithEff ? "bg-[var(--pv-accent)]" : "bg-white"}`}
          >
            <span
              className={`absolute top-[3px] w-3 h-3 bg-black transition-transform ${filter.onlyWithEff ? "translate-x-[18px] !bg-white" : "translate-x-[3px]"}`}
              aria-hidden="true"
            />
          </button>
          <span className="text-[13px]">仅显示含效应量（HR/RR/CI）</span>
        </label>

        <button type="button" onClick={onReset} className="pv-chip w-full py-2.5">
          重置筛选 · Reset
        </button>
      </div>
    </aside>
  );
}

function countBy(list: Relation[], key: (r: Relation) => string) {
  const m: Record<string, number> = {};
  for (const r of list) m[key(r)] = (m[key(r)] ?? 0) + 1;
  return m;
}
