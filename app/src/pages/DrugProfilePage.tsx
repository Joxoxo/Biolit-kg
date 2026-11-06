// 药物安全档案：选一个药，看①它相对各种对照药的疗效与安全性结论，②它的相互作用与代谢，以及与说明书的比对
import { useEffect, useMemo, useState } from "react";
import {
  getDrugs, getEvidence, getProfile,
  type Comparison, type DrugOption, type DrugProfile, type EvidencePaper, type Mechanism,
} from "@/lib/api";
import EgoGraph from "@/sections/EgoGraph";
import { mechStatus } from "@/sections/status";

// 常见名称的中文对照；没有的直接显示英文
const ZH: Record<string, string> = {
  warfarin: "华法林", apixaban: "阿哌沙班", rivaroxaban: "利伐沙班", dabigatran: "达比加群", edoxaban: "依度沙班",
  clopidogrel: "氯吡格雷", ticagrelor: "替格瑞洛", aspirin: "阿司匹林", prasugrel: "普拉格雷", doac: "DOAC",
  "vitamin k antagonist": "维生素 K 拮抗剂", "low-molecular-weight heparin": "低分子肝素", placebo: "安慰剂",
  bleeding: "出血", "major bleeding": "大出血", "gastrointestinal bleeding": "消化道出血",
  "major gastrointestinal bleeding": "大消化道出血", "intracranial hemorrhage": "颅内出血",
  "crnm bleeding": "临床相关非大出血", "minor bleeding": "小出血", stroke: "卒中", "ischemic stroke": "缺血性卒中",
  "hemorrhagic stroke": "出血性卒中", "stroke or systemic embolism": "卒中或体循环栓塞",
  "systemic embolism": "体循环栓塞", "all-cause mortality": "全因死亡", "cardiovascular death": "心血管死亡",
  mace: "主要不良心血管事件", "myocardial infarction": "心肌梗死", "recurrent vte": "VTE 复发",
  "venous thromboembolism": "静脉血栓栓塞", thromboembolism: "血栓栓塞", "thrombotic event": "血栓事件",
  "stent thrombosis": "支架内血栓", dyspnea: "呼吸困难",
};
const zh = (x: string) => ZH[x] || x;
const STUDY_ZH: Record<string, string> = {
  meta_analysis: "Meta", rct: "RCT", observational: "观察", clinical_pk: "药代", review: "综述",
  case_report: "病例", preclinical: "临床前", other: "其他",
};
const REL_ZH: Record<string, string> = {
  interacts_with: "相互作用", inhibits: "抑制", induces: "诱导", metabolized_by: "被代谢", transported_by: "被转运",
};
const TYPES = [
  { id: "all", label: "全部" },
  { id: "adverse_event", label: "不良事件" },
  { id: "outcome", label: "临床结局" },
];

export default function DrugProfilePage() {
  const [drugs, setDrugs] = useState<DrugOption[]>([]);
  const [drug, setDrug] = useState("apixaban");
  const [profile, setProfile] = useState<DrugProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDrugs().then(setDrugs).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    setProfile(null);
    setError(null);
    getProfile(drug).then(setProfile).catch((e) => setError(e.message));
  }, [drug]);

  return (
    <div className="flex-1 overflow-y-auto pv-scroll">
      <div className="max-w-[1400px] mx-auto px-6 md:px-8 py-8 space-y-8">
        <div className="space-y-3">
          <h2 className="text-[22px] font-bold">药物安全档案</h2>
          <label className="block">
            <span className="sr-only">选择药物</span>
            <select
              value={drug}
              onChange={(e) => setDrug(e.target.value)}
              className="w-full pv-border bg-white px-4 py-3 text-[16px] font-bold cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--pv-accent)]"
            >
              {(drugs.length ? drugs : [{ id: "apixaban", zh: "阿哌沙班" }]).map((d) => (
                <option key={d.id} value={d.id}>{d.zh}（{d.id}）</option>
              ))}
            </select>
          </label>
        </div>

        {error && <div className="pv-border p-4 text-[var(--pv-bad)] text-[13.5px]">加载失败：{error}</div>}
        {!profile && !error && <div className="text-black/50 text-[13.5px] py-10 text-center">加载中…</div>}
        {profile && (
          <>
            <Summary p={profile} />
            <ComparisonSection p={profile} />
            <MechanismSection p={profile} />
          </>
        )}
      </div>
    </div>
  );
}

function Summary({ p }: { p: DrugProfile }) {
  const cards = [
    { label: "涉及文献", value: p.n_papers, note: "篇" },
    { label: "比较结论", value: p.n_comparisons, note: "组（对照药 × 结局）" },
    { label: "结论不一致", value: p.n_conflicts, note: "组，相反方向 ≥ 2 篇", tone: "var(--pv-warn)" },
    { label: "潜在信号", value: p.n_signals, note: "项，说明书未涵盖（人工确认）", tone: "var(--pv-bad)" },
  ];
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((c) => (
        <div key={c.label} className="pv-border p-4 bg-white">
          <div className="pv-label">{c.label}</div>
          <div className="mono text-[28px] font-bold mt-1" style={{ color: c.tone }}>{c.value}</div>
          <div className="text-[12px] text-black/50">{c.note}</div>
        </div>
      ))}
    </div>
  );
}

// ---------- ① 疗效与安全性比较 ----------

function ComparisonSection({ p }: { p: DrugProfile }) {
  const [type, setType] = useState("all");
  const [minPapers, setMinPapers] = useState(2);
  const [onlyMixed, setOnlyMixed] = useState(false);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const groups = useMemo(() => {
    const rows = p.comparisons.filter((c) =>
      (type === "all" || c.outcome_type === type) && c.n_papers >= minPapers && (!onlyMixed || c.direction === "mixed"));
    const map = new Map<string, Comparison[]>();
    rows.forEach((c) => map.set(c.comparator, [...(map.get(c.comparator) || []), c]));
    // 组按文献总数排序；"未指明对照"放最后
    return [...map.entries()].sort((a, b) =>
      (a[0] === "" ? 1 : 0) - (b[0] === "" ? 1 : 0) ||
      b[1].reduce((s, c) => s + c.n_papers, 0) - a[1].reduce((s, c) => s + c.n_papers, 0));
  }, [p, type, minPapers, onlyMixed]);

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-[17px] font-bold">① 疗效与安全性比较</h3>
        <div className="flex flex-wrap items-center gap-3 text-[12.5px]">
          <div className="flex pv-border">
            {TYPES.map((t) => (
              <button key={t.id} type="button" onClick={() => setType(t.id)}
                className={`px-3 py-1.5 ${type === t.id ? "bg-black text-white" : "bg-white hover:bg-black/[0.04]"}`}>
                {t.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2">
            至少
            <select value={minPapers} onChange={(e) => setMinPapers(Number(e.target.value))}
              className="pv-border bg-white px-2 py-1">
              {[1, 2, 3, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            篇文献
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={onlyMixed} onChange={(e) => setOnlyMixed(e.target.checked)} />
            只看结论不一致
          </label>
        </div>
      </div>

      {groups.length === 0 && <div className="pv-border p-6 text-center text-black/50 text-[13px]">没有符合条件的结论</div>}
      {groups.map(([comparator, rows]) => {
        const key = comparator || "_none";
        const shown = open[key] ? rows : rows.slice(0, 6);
        return (
          <div key={key} className="pv-border bg-white">
            <div className="px-4 py-2.5 pv-border-b bg-black/[0.03] flex items-baseline justify-between">
              <span className="font-bold text-[14px]">
                {comparator ? <>相比 {zh(comparator)} <span className="mono text-[12px] text-black/45 font-normal">{comparator !== zh(comparator) && comparator}</span></> : "文献未指明对照"}
              </span>
              <span className="text-[12px] text-black/50">{rows.length} 项</span>
            </div>
            <div className="hidden md:grid grid-cols-[minmax(0,1.6fr)_150px_70px_minmax(0,1.2fr)] gap-3 px-4 py-1.5 pv-label border-b border-black/10">
              <span>结局</span><span>结论</span><span>文献</span><span>研究类型</span>
            </div>
            {shown.map((c) => <ComparisonRow key={c.outcome} drug={p.drug} c={c} />)}
            {rows.length > 6 && (
              <button type="button" onClick={() => setOpen({ ...open, [key]: !open[key] })}
                className="w-full text-[12.5px] py-2 text-[var(--pv-accent)] font-bold hover:bg-black/[0.02]">
                {open[key] ? "收起" : `展开全部 ${rows.length} 项`}
              </button>
            )}
          </div>
        );
      })}
    </section>
  );
}

function Direction({ c }: { c: Comparison }) {
  const map = {
    decreases: { text: "↓ 降低", color: "var(--pv-ok)" },
    increases: { text: "↑ 增加", color: "var(--pv-bad)" },
    mixed: { text: "⚠ 不一致", color: "var(--pv-warn)" },
  }[c.direction];
  const minority = Math.min(c.n_dec, c.n_inc);
  return (
    <span className="flex items-center gap-2">
      <span className="font-bold" style={{ color: map.color }}>{map.text}</span>
      {c.direction === "mixed" && <span className="mono text-[11.5px] text-black/55">{c.n_dec}↓ / {c.n_inc}↑</span>}
      {c.direction !== "mixed" && minority === 1 && <span className="text-[11.5px] text-black/45">（1 篇相反）</span>}
    </span>
  );
}

function ComparisonRow({ drug, c }: { drug: string; c: Comparison }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border-b border-black/10 last:border-b-0">
      <button type="button" onClick={() => setExpanded(!expanded)}
        className="w-full text-left grid grid-cols-1 md:grid-cols-[minmax(0,1.6fr)_150px_70px_minmax(0,1.2fr)] gap-x-3 gap-y-1 px-4 py-2.5 text-[13.5px] hover:bg-[var(--pv-accent-soft)]">
        <span className="min-w-0">
          <span className="font-bold">{zh(c.outcome)}</span>
          {zh(c.outcome) !== c.outcome && <span className="mono text-[11.5px] text-black/45 ml-2">{c.outcome}</span>}
        </span>
        <Direction c={c} />
        <span className="mono">{c.n_papers}</span>
        <span className="text-[12px] text-black/60 truncate">
          {Object.entries(c.study_types).map(([k, v]) => `${STUDY_ZH[k] || k} ${v}`).join(" · ")}
        </span>
      </button>
      {expanded && <Evidence pmids={c.pmids} a={drug} b={c.outcome} />}
    </div>
  );
}

// 展开某一行：取对应文献的标题和证据句
function Evidence({ pmids, a, b, extra }: { pmids: number[]; a: string; b: string; extra?: React.ReactNode }) {
  const [papers, setPapers] = useState<EvidencePaper[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getEvidence(pmids, a, b).then(setPapers).catch((e) => setError(e.message));
  }, [pmids, a, b]);
  return (
    <div className="px-4 pb-4 pt-1 bg-black/[0.02] space-y-3 text-[13px]">
      {extra}
      {error && <div className="text-[var(--pv-bad)]">加载证据失败：{error}</div>}
      {!papers && !error && <div className="text-black/50">加载证据…</div>}
      {papers?.map((pp) => (
        <div key={pp.pmid} className="space-y-1">
          <div className="text-[12.5px]">
            <a href={`https://pubmed.ncbi.nlm.nih.gov/${pp.pmid}/`} target="_blank" rel="noreferrer"
              className="mono text-[var(--pv-accent)] hover:underline mr-2">PMID {pp.pmid}</a>
            <span className="text-black/50">{pp.year} · {STUDY_ZH[pp.study_type || ""] || pp.study_type || "—"}</span>
            <span className="block text-black/75">{pp.title}</span>
          </div>
          {pp.sentences.map((s, i) => (
            <blockquote key={i} className="border-l-[3px] border-[var(--pv-accent)] pl-3 text-black/70 leading-relaxed">{s}</blockquote>
          ))}
        </div>
      ))}
      {pmids.length > 20 && <div className="text-[12px] text-black/45">只显示最近的 20 篇，共 {pmids.length} 篇。</div>}
    </div>
  );
}

// ---------- ② 相互作用与代谢 ----------

const FILTERS = [
  { id: "all", label: "全部" },
  { id: "signal", label: "潜在信号" },
  { id: "conflict", label: "与说明书冲突" },
  { id: "covered", label: "说明书已涵盖" },
];

function MechanismSection({ p }: { p: DrugProfile }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const items = useMemo(() => p.mechanisms.filter((m) => filter === "all" || mechStatus(m).key === filter), [p, filter]);

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-[17px] font-bold">② 相互作用与代谢</h3>
        <div className="flex pv-border text-[12.5px]">
          {FILTERS.map((f) => (
            <button key={f.id} type="button" onClick={() => { setFilter(f.id); setSelected(null); }}
              className={`px-3 py-1.5 ${filter === f.id ? "bg-black text-white" : "bg-white hover:bg-black/[0.04]"}`}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-4">
        <div className="pv-border bg-[#fafafa] relative h-[460px]">
          {items.length > 0
            ? <EgoGraph drug={p.drug} drugLabel={p.drug_zh} items={items} selected={selected} onSelect={setSelected} />
            : <div className="absolute inset-0 flex items-center justify-center text-black/50 text-[13px]">没有符合条件的项目</div>}
          <Legend />
        </div>
        <div className="pv-border bg-white max-h-[460px] overflow-y-auto pv-scroll">
          {items.map((m) => (
            <MechanismRow key={m.partner} drug={p.drug} m={m} open={selected === m.partner}
              onToggle={() => setSelected(selected === m.partner ? null : m.partner)} />
          ))}
        </div>
      </div>
    </section>
  );
}

function Legend() {
  const rows = [
    ["#c2271a", "潜在信号"], ["#b45309", "与说明书冲突"], ["#047857", "说明书已涵盖"], ["#868e96", "未审核"],
  ];
  return (
    <div className="absolute left-3 bottom-3 bg-white/90 pv-border px-3 py-2 text-[11px] space-y-1">
      {rows.map(([c, t]) => (
        <div key={t} className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />{t}</div>
      ))}
      <div className="text-black/45">▲ 酶 / 转运体　● 药物</div>
    </div>
  );
}

function MechanismRow({ drug, m, open, onToggle }: { drug: string; m: Mechanism; open: boolean; onToggle: () => void }) {
  const st = mechStatus(m);
  const extra = (m.label_evidence || m.review_note) && (
    <div className="space-y-1 text-[12.5px]">
      {m.label_evidence && <div><span className="pv-label mr-2">说明书原文</span><span className="text-black/70">{m.label_evidence}</span></div>}
      {m.review_note && <div><span className="pv-label mr-2">审核备注</span><span className="text-black/70">{m.review_note}</span></div>}
    </div>
  );
  return (
    <div className="border-b border-black/10 last:border-b-0">
      <button type="button" onClick={onToggle}
        className={`w-full text-left px-4 py-2.5 flex items-center gap-3 text-[13.5px] hover:bg-[var(--pv-accent-soft)] ${open ? "bg-[var(--pv-accent-soft)]" : ""}`}>
        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: st.color }} />
        <span className="flex-1 min-w-0">
          <span className="font-bold mono">{m.partner}</span>
          <span className="text-[12px] text-black/50 ml-2">{m.relations.map((r) => REL_ZH[r] || r).join("、")}</span>
        </span>
        <span className="text-[12px] whitespace-nowrap" style={{ color: st.color }}>{st.label}</span>
        <span className="mono text-[12px] text-black/50 w-10 text-right">{m.n_papers} 篇</span>
      </button>
      {open && <Evidence pmids={m.pmids} a={drug} b={m.partner} extra={extra} />}
    </div>
  );
}
