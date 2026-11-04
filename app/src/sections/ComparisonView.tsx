import { useMemo, useState } from "react";
import type { Relation } from "@/types/pv";

/* ---------- drug / outcome normalization ---------- */

export function normDrug(s: string) {
  return s
    .trim()
    .toLowerCase()
    .replace(/^continuing\s+/, "")
    .replace(/^standard-intensity\s+/, "");
}

function isRiskOutcome(object: string) {
  // 含 benefit 的结局方向相反：降低 benefit = 劣势
  return !/benefit/i.test(object);
}

/** direction: +1 = A 更优, -1 = A 更差, 0 = 无方向（机制类） */
function directionOf(r: Relation, a: string): number {
  if (r.relation !== "降低风险" && r.relation !== "增加风险") return 0;
  let d = r.relation === "降低风险" ? 1 : -1;
  if (normDrug(r.subject) !== a) d = -d; // 反向关系（B vs A）
  if (!isRiskOutcome(r.object)) d = -d;
  return d;
}

type OutcomeGroup = {
  key: string;
  object: string;
  favorable: number;
  unfavorable: number;
  items: Relation[];
};

/* ---------- main component ---------- */

export function ComparisonView({
  relations,
  all,
  selected,
  onSelect,
  drugA,
  drugB,
  onDrugsChange,
}: {
  relations: Relation[]; // 已应用全局筛选
  all: Relation[];
  selected: Relation | null;
  onSelect: (r: Relation) => void;
  drugA: string;
  drugB: string;
  onDrugsChange: (a: string, b: string) => void;
}) {
  const drugOptions = useMemo(() => buildDrugOptions(all), [all]);

  const matched = useMemo(() => {
    if (!drugA || !drugB || drugA === drugB) return [];
    return relations.filter(
      (r) =>
        (normDrug(r.subject) === drugA && normDrug(r.comparator) === drugB) ||
        (normDrug(r.subject) === drugB && normDrug(r.comparator) === drugA),
    );
  }, [relations, drugA, drugB]);

  const { outcomes, mechanisms } = useMemo(() => {
    const groups = new Map<string, OutcomeGroup>();
    const mech: Relation[] = [];
    for (const r of matched) {
      const d = directionOf(r, drugA);
      if (d === 0) {
        mech.push(r);
        continue;
      }
      const key = r.object.trim().toLowerCase();
      if (!groups.has(key)) groups.set(key, { key, object: r.object, favorable: 0, unfavorable: 0, items: [] });
      const g = groups.get(key)!;
      g.items.push(r);
      if (d > 0) g.favorable++;
      else g.unfavorable++;
    }
    const list = [...groups.values()].sort((x, y) => y.items.length - x.items.length);
    return { outcomes: list, mechanisms: mech };
  }, [matched, drugA]);

  const totalFav = outcomes.reduce((s, g) => s + g.favorable, 0);
  const totalUnfav = outcomes.reduce((s, g) => s + g.unfavorable, 0);
  const displayA = drugOptions.find((d) => d.key === drugA)?.label ?? drugA;
  const displayB = drugOptions.find((d) => d.key === drugB)?.label ?? drugB;

  return (
    <div className="flex-1 min-w-0 overflow-y-auto pv-scroll">
      {/* drug pickers */}
      <div className="pv-border-b bg-white px-4 py-4 sticky top-0 z-20">
        <div className="pv-label mb-2">药物对比 · Drug Comparison</div>
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <DrugSelect value={drugA} options={drugOptions} onChange={(v) => onDrugsChange(v, drugB)} ariaLabel="药物 A" />
          </div>
          <span className="mono text-[13px] text-black/50 shrink-0">vs</span>
          <div className="flex-1 min-w-0">
            <DrugSelect value={drugB} options={drugOptions} onChange={(v) => onDrugsChange(drugA, v)} ariaLabel="药物 B" />
          </div>
          <button
            type="button"
            className="pv-chip shrink-0"
            aria-label="交换两种药物"
            onClick={() => onDrugsChange(drugB, drugA)}
          >
            交换 ⇄
          </button>
        </div>
      </div>

      {/* summary */}
      {drugA && drugB && drugA !== drugB && (
        <div className="px-4 py-5 pv-border-b">
          {matched.length === 0 ? (
            <div className="pv-border border-dashed p-6 text-center">
              <div className="text-[13px] text-black/60">
                当前筛选下没有 {displayA} 与 {displayB} 的直接对比证据，可尝试重置筛选或更换药物。
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
                <BigVerdict n={totalFav} label={`${displayA} 更优`} tone="ok" />
                <BigVerdict n={totalUnfav} label={`${displayB} 更优`} tone="bad" />
                <div className="text-[12px] text-black/55 pb-1">
                  共 {matched.length} 条对比证据 · 覆盖 {outcomes.length} 个结局
                  {mechanisms.length > 0 && ` · 机制类 ${mechanisms.length} 条`}
                </div>
              </div>
              {/* advantage bar */}
              {totalFav + totalUnfav > 0 && (
                <div className="mt-4">
                  <div className="flex h-3.5 w-full max-w-xl pv-border" role="img"
                    aria-label={`${displayA} 更优 ${totalFav} 条，${displayB} 更优 ${totalUnfav} 条`}>
                    <div style={{ width: `${(totalFav / (totalFav + totalUnfav)) * 100}%`, background: "var(--pv-ok)" }} />
                    <div style={{ width: `${(totalUnfav / (totalFav + totalUnfav)) * 100}%`, background: "var(--pv-bad)" }} />
                  </div>
                  <div className="flex justify-between max-w-xl mt-1.5 mono text-[10.5px] text-black/55">
                    <span>{displayA} 更优 {Math.round((totalFav / (totalFav + totalUnfav)) * 100)}%</span>
                    <span>{displayB} 更优 {Math.round((totalUnfav / (totalFav + totalUnfav)) * 100)}%</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* outcome cards */}
      <div className="divide-y divide-black/12">
        {outcomes.map((g) => (
          <OutcomeCard key={g.key} group={g} a={displayA} b={displayB} onSelect={onSelect} selected={selected} />
        ))}

        {/* mechanism group */}
        {mechanisms.length > 0 && (
          <div className="px-4 py-4">
            <div className="pv-label mb-3">机制与相互作用 · Mechanism（不参与优劣判定）</div>
            <div className="space-y-2">
              {mechanisms.map((r, i) => (
                <EvidenceItem key={`m-${i}`} r={r} a={drugA} onSelect={onSelect} selected={selected} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- pieces ---------- */

function DrugSelect({
  value, options, onChange, ariaLabel,
}: {
  value: string;
  options: { key: string; label: string }[];
  onChange: (v: string) => void;
  ariaLabel: string;
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="mono text-[13px] font-bold pv-border bg-white px-3 py-2 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--pv-accent)] w-full"
    >
      {options.map((o) => (
        <option key={o.key} value={o.key}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function BigVerdict({ n, label, tone }: { n: number; label: string; tone: "ok" | "bad" }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className={`mono font-bold text-[34px] leading-none ${tone === "ok" ? "text-[var(--pv-ok)]" : "text-[var(--pv-bad)]"}`}>
        {n}
      </span>
      <span className="text-[13px] text-black/70">条证据显示 {label}</span>
    </div>
  );
}

function OutcomeCard({
  group, a, b, onSelect, selected,
}: {
  group: OutcomeGroup;
  a: string;
  b: string;
  onSelect: (r: Relation) => void;
  selected: Relation | null;
}) {
  const [open, setOpen] = useState(false);
  const verdict =
    group.unfavorable === 0 ? { text: `${a} 更优`, cls: "text-[var(--pv-ok)]" }
    : group.favorable === 0 ? { text: `${b} 更优`, cls: "text-[var(--pv-bad)]" }
    : { text: "证据不一致", cls: "text-[var(--pv-warn)]" };

  return (
    <div className="px-4 py-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full flex items-center gap-3 text-left group cursor-pointer"
      >
        <span className="mono text-[12px] text-black/40 w-5 shrink-0">{open ? "−" : "+"}</span>
        <span className="font-medium text-[14px] break-words">{group.object}</span>
        <span className={`pv-pill ${verdict.cls} shrink-0`}>{verdict.text}</span>
        <span className="mono text-[11px] text-black/45 ml-auto shrink-0">{group.items.length} 条证据</span>
      </button>
      {open && (
        <div className="mt-3 ml-8 space-y-2">
          {group.items.map((r, i) => (
            <EvidenceItem key={i} r={r} a={a} onSelect={onSelect} selected={selected} />
          ))}
        </div>
      )}
    </div>
  );
}

function EvidenceItem({
  r, a, onSelect, selected,
}: {
  r: Relation;
  a: string;
  onSelect: (r: Relation) => void;
  selected: Relation | null;
}) {
  const d = directionOf(r, normDrug(a));
  const isSel = selected === r;
  const dirText = d > 0 ? "↑ 优势" : d < 0 ? "↓ 劣势" : "· 机制";
  const dirCls = d > 0 ? "text-[var(--pv-ok)]" : d < 0 ? "text-[var(--pv-bad)]" : "text-black/45";
  return (
    <button
      type="button"
      onClick={() => onSelect(r)}
      aria-pressed={isSel}
      className={`w-full text-left pv-border px-3 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 transition-colors cursor-pointer ${
        isSel ? "bg-[var(--pv-accent-soft)] border-[var(--pv-accent)]" : "bg-white hover:bg-black/[0.025]"
      }`}
    >
      <span className={`mono text-[11px] font-bold ${dirCls} shrink-0`}>{dirText}</span>
      <span className="mono text-[11.5px] text-black/80">{r.effect || r.relation}</span>
      <span className="mono text-[10.5px] text-black/45 ml-auto shrink-0">
        PMID {r.pmid}
      </span>
      <span className="mono text-[10.5px] text-[var(--pv-accent)] shrink-0">阅读证据 →</span>
    </button>
  );
}

/* ---------- drug options ---------- */

function buildDrugOptions(relations: Relation[]) {
  const counts = new Map<string, { label: string; n: number }>();
  for (const r of relations) {
    for (const raw of [r.subject, r.comparator]) {
      if (!raw) continue;
      const k = normDrug(raw);
      if (!k) continue;
      const cur = counts.get(k);
      if (!cur) counts.set(k, { label: raw.trim(), n: 1 });
      else cur.n++;
    }
  }
  return [...counts.entries()]
    .map(([key, v]) => ({ key, label: v.label, n: v.n }))
    .sort((a, b) => b.n - a.n)
    .map(({ key, label }) => ({ key, label }));
}
