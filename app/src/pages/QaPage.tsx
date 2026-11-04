import { useState } from "react";
import { askQuestion, type AskResult } from "@/lib/api";

const EXAMPLES = [
  "阿哌沙班和华法林相比，大出血风险怎么样？",
  "哪些药物会通过 CYP3A4 影响替格瑞洛的血药浓度？",
  "达比加群会增加消化道出血吗？",
];

export default function QaPage() {
  const [question, setQuestion] = useState("");
  const [k, setK] = useState(5);
  const [result, setResult] = useState<AskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await askQuestion({ question: question.trim(), k });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto pv-scroll">
      <div className="max-w-5xl mx-auto px-8 py-10 space-y-8">
        <div>
          <h2 className="text-[22px] font-bold">智能问答 · RAG Q&A</h2>
          <p className="text-[14px] text-black/60 mt-2">
            混合检索（向量 + 实体匹配 + 知识图谱）后交由大模型生成回答，每个结论附 PMID 引用。
          </p>
        </div>

        <form onSubmit={handleSubmit} className="pv-border p-6 space-y-4 bg-white">
          <div>
            <label className="pv-label mb-2 block">问题 · Question</label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="输入关于口服抗栓药物的问题…"
              rows={4}
              className="w-full px-3 py-2 pv-border bg-white text-[14px] focus:outline-none focus:ring-2 focus:ring-[var(--pv-accent)] resize-none"
            />
            <div className="flex flex-wrap gap-2 mt-3">
              {EXAMPLES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuestion(q)}
                  className="pv-chip text-[12px]"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="pv-label">检索文献数</label>
              <select
                value={k}
                onChange={(e) => setK(Number(e.target.value))}
                className="pv-border px-2 py-1 text-[13px] bg-white"
              >
                {[3, 5, 8, 10].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="pv-chip pv-chip-accent ml-auto disabled:opacity-50"
            >
              {loading ? "思考中…" : "提交问题"}
            </button>
          </div>
        </form>

        {error && (
          <div className="pv-border px-4 py-3 text-[13px] text-[var(--pv-bad)] bg-[var(--pv-bad)]/5">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-6">
            <section className="pv-border p-6 bg-white">
              <h3 className="font-bold text-[15.5px] mb-4">回答 · Answer</h3>
              <div className="text-[15.5px] leading-relaxed whitespace-pre-wrap text-black/85">
                {result.answer}
              </div>
              {result.invalid_citations.length > 0 && (
                <div className="mt-3 text-[12px] text-[var(--pv-bad)]">
                  ⚠️ 检测到无效引用（不在本次检索结果中）：{result.invalid_citations.join(", ")}
                </div>
              )}
            </section>

            {result.graph_facts.length > 0 && (
              <section className="pv-border p-6 bg-white">
                <h3 className="font-bold text-[15.5px] mb-4">知识图谱结论 · Graph Facts</h3>
                <ul className="space-y-2.5 text-[14px]">
                  {result.graph_facts.map((f, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-[var(--pv-accent)]">●</span>
                      <span>
                        {f.subject} {REL_ZH[f.relation] || f.relation} {f.object}
                        {f.comparator && `（对照：${f.comparator}）`}
                        <span className="text-black/50 ml-1">— {f.n_papers} 篇文献支持</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="pv-border p-6 bg-white">
              <h3 className="font-bold text-[15.5px] mb-4">引用文献 · Citations</h3>
              <div className="space-y-4">
                {result.papers.map((p) => (
                  <div key={p.pmid} className="text-[13.5px] leading-relaxed border-l-2 border-black/10 pl-4">
                    <div className="font-bold">
                      <a
                        href={`https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[var(--pv-accent)] hover:underline"
                      >
                        PMID {p.pmid}
                      </a>
                      <span className="text-black/50 font-normal ml-2">
                        {p.year} · {p.study_type || "未知类型"} · 匹配 {p.matched.join("、")}
                      </span>
                    </div>
                    <div className="text-black/80">{p.title}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

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
