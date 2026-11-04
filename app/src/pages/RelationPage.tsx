import { useMemo, useState } from "react";
import raw from "@/data/relations.json";
import { FilterRail } from "@/sections/FilterRail";
import { RelationTable, useFiltered } from "@/sections/RelationTable";
import { ComparisonView } from "@/sections/ComparisonView";
import { DetailDrawer } from "@/sections/DetailDrawer";
import type { PvData, Relation, FilterState } from "@/types/pv";

const data = raw as unknown as PvData;

const DEFAULT_FILTER: FilterState = {
  q: "",
  relations: new Set(),
  onlyWithEff: false,
};

type Mode = "compare" | "browse";

export default function RelationPage() {
  const [filter, setFilter] = useState<FilterState>(DEFAULT_FILTER);
  const [selected, setSelected] = useState<Relation | null>(null);
  const [mode, setMode] = useState<Mode>("compare");
  const [drugA, setDrugA] = useState("apixaban");
  const [drugB, setDrugB] = useState("warfarin");

  const relations = useMemo(() => data.relations, []);
  const filtered = useFiltered(relations, filter);

  const handleSelect = (r: Relation) => setSelected((cur) => (cur === r ? null : r));

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <div className="flex flex-col lg:flex-row flex-1 min-h-0">
        <FilterRail
          all={relations}
          filter={filter}
          onChange={(f) => setFilter(f)}
          onReset={() => {
            setFilter(DEFAULT_FILTER);
            setSelected(null);
          }}
        />

        <div className="flex-1 min-w-0 min-h-0 flex flex-col">
          {/* mode tabs */}
          <div className="flex pv-border-b bg-white sticky top-0 z-30" role="tablist" aria-label="视图模式">
            {(
              [
                { key: "compare", label: "药物对比查询" },
                { key: "browse", label: "全部关系索引" },
              ] as const
            ).map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={mode === t.key}
                onClick={() => {
                  setMode(t.key);
                  setSelected(null);
                }}
                className={`px-5 py-3 text-[13px] mono font-bold transition-colors cursor-pointer ${
                  mode === t.key
                    ? "text-[var(--pv-accent)] border-b-2 border-[var(--pv-accent)]"
                    : "text-black/45 hover:text-black"
                }`}
              >
                {t.label}
              </button>
            ))}
            {mode === "browse" && (
              <div className="ml-auto flex items-center px-5 mono text-[12px] text-black/60">
                显示 <span className="text-[var(--pv-accent)] font-bold">{filtered.length}</span> / {relations.length} 条
              </div>
            )}
          </div>

          {mode === "compare" ? (
            <ComparisonView
              relations={filtered}
              all={relations}
              selected={selected}
              onSelect={handleSelect}
              drugA={drugA}
              drugB={drugB}
              onDrugsChange={(a, b) => {
                setDrugA(a);
                setDrugB(b);
              }}
            />
          ) : (
            <RelationTable relations={filtered} selected={selected} onSelect={handleSelect} papers={data.papers} />
          )}
        </div>

        <DetailDrawer relation={selected} papers={data.papers} onClose={() => setSelected(null)} />
      </div>
    </div>
  );
}
