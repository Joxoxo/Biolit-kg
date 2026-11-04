import { useState } from "react";
import { extractText, type ExtractResult } from "@/lib/api";

const TYPE_ZH: Record<string, string> = {
  drug: "药物",
  adverse_event: "不良事件",
  outcome: "临床结局",
  disease: "疾病",
  enzyme: "酶 / 转运体",
  population: "人群",
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

export default function ExtractPage() {
  const [title, setTitle] = useState("");
  const [abstract, setAbstract] = useState("");
  const [result, setResult] = useState<ExtractResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !abstract.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extractText({ title: title.trim(), abstract: abstract.trim() });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto pv-scroll">
      <div className="max-w-[1600px] mx-auto px-8 py-10">
        <div className="mb-8">
          <h2 className="text-[22px] font-bold">在线抽取 · Online Extraction</h2>
          <p className="text-[14px] text-black/60 mt-2">
            输入一篇文献的标题与摘要，调用 Gemini 抽取实体、关系与研究类型（消耗 API 额度）。
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-6 items-start">
          <form onSubmit={handleSubmit} className="pv-border p-6 space-y-4 bg-white w-full lg:w-[440px] shrink-0 lg:sticky lg:top-10">
            <div>
              <label className="pv-label mb-2 block">标题 · Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="文献标题"
                className="w-full px-3 py-2 pv-border bg-white text-[14px] focus:outline-none focus:ring-2 focus:ring-[var(--pv-accent)]"
              />
            </div>
            <div>
              <label className="pv-label mb-2 block">摘要 · Abstract</label>
              <textarea
                value={abstract}
                onChange={(e) => setAbstract(e.target.value)}
                placeholder="文献摘要"
                rows={10}
                className="w-full px-3 py-2 pv-border bg-white text-[14px] leading-relaxed focus:outline-none focus:ring-2 focus:ring-[var(--pv-accent)] resize-y"
              />
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={loading || !title.trim() || !abstract.trim()}
                className="pv-chip pv-chip-accent disabled:opacity-50"
              >
                {loading ? "抽取中…" : "执行抽取"}
              </button>
            </div>
          </form>

          <div className="flex-1 min-w-0 w-full space-y-6">
            {error && (
              <div className="pv-border px-4 py-3 text-[13.5px] text-[var(--pv-bad)] bg-[var(--pv-bad)]/5">
                {error}
              </div>
            )}

            {result ? (
              <>
                <div className="pv-border p-5 bg-white flex flex-wrap gap-x-8 gap-y-3 text-[13px]">
                  <span>
                    <span className="pv-label">研究类型</span>{" "}
                    <span className="mono font-bold">{result.study_type}</span>
                  </span>
                  <span>
                    <span className="pv-label">模型</span>{" "}
                    <span className="mono">{result.model}</span>
                  </span>
                  <span>
                    <span className="pv-label">Token</span>{" "}
                    <span className="mono">{result.input_tokens} → {result.output_tokens}</span>
                  </span>
                  <span>
                    <span className="pv-label">耗时</span>{" "}
                    <span className="mono">{result.seconds}s</span>
                  </span>
                </div>

                <section className="pv-border p-6 bg-white">
                  <h3 className="font-bold text-[15.5px] mb-4">实体 · Entities（{result.entities.length}）</h3>
                  <div className="flex flex-wrap gap-2">
                    {result.entities.map((e, i) => (
                      <span key={i} className="pv-chip">
                        {e.name}
                        <span className="text-black/50 ml-1">{TYPE_ZH[e.type] || e.type}</span>
                      </span>
                    ))}
                  </div>
                </section>

                <section className="pv-border p-6 bg-white">
                  <h3 className="font-bold text-[15.5px] mb-4">关系 · Relations（{result.relations.length}）</h3>
                  <div className="space-y-3">
                    {result.relations.map((r, i) => (
                      <div key={i} className="pv-border p-4 text-[14px]">
                        <div className="font-bold mb-1.5">
                          {r.subject} → {REL_ZH[r.relation] || r.relation} → {r.object}
                        </div>
                        <div className="text-black/60 space-y-0.5">
                          {r.comparator && <div>对照：{r.comparator}</div>}
                          {r.effect && <div>效果：{r.effect}</div>}
                          {r.population && <div>人群：{r.population}</div>}
                        </div>
                        <blockquote className="mt-3 pv-border-l-2 border-l-[3px] border-[var(--pv-accent)] pl-3 text-black/70 italic leading-relaxed">
                          {r.evidence}
                        </blockquote>
                      </div>
                    ))}
                  </div>
                </section>
              </>
            ) : (
              !error && (
                <div className="pv-border border-dashed p-8 text-[13.5px] text-black/50 leading-relaxed">
                  在左侧输入文献标题与摘要，点击「执行抽取」后，实体与关系结果将显示在这里。
                </div>
              )
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
