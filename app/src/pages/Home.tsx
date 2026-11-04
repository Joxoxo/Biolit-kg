import { Database, MessageCircle, Network, Microscope } from "lucide-react";

const SECTIONS = [
  { id: "relations", label: "关系索引", icon: Database, desc: "浏览 60 篇人工标注文献中的药物–结局关系" },
  { id: "graph", label: "知识图谱", icon: Network, desc: "交互式查看 648 个实体、1538 条关系" },
  { id: "qa", label: "智能问答", icon: MessageCircle, desc: "基于向量检索 + 图谱的 RAG 问答，带 PMID 引用" },
  { id: "extract", label: "在线抽取", icon: Microscope, desc: "输入标题与摘要，调用大模型抽取实体和关系" },
];

export default function Home({ onNavigate }: { onNavigate: (id: string) => void }) {
  return (
    <div className="flex-1 overflow-y-auto pv-scroll px-8 py-10">
      <div className="max-w-7xl mx-auto space-y-10">
        <div>
          <h1 className="text-[28px] font-bold tracking-tight">BioLit-KG 工作台</h1>
          <p className="text-[14.5px] text-black/60 mt-2">
            基于大模型的生物医学文献知识图谱与智能问答平台 · 口服抗栓药物药物警戒方向
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {SECTIONS.map((s) => {
            const Icon = s.icon;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => onNavigate(s.id)}
                className="text-left pv-border p-6 bg-white hover:bg-black/[0.02] transition-colors group"
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className="w-10 h-10 flex items-center justify-center bg-[var(--pv-accent-soft)] text-[var(--pv-accent)]">
                    <Icon size={20} />
                  </span>
                  <span className="font-bold text-[15.5px]">{s.label}</span>
                </div>
                <p className="text-[13.5px] text-black/60 leading-relaxed">{s.desc}</p>
                <span className="inline-block mt-4 text-[12px] text-[var(--pv-accent)] font-bold group-hover:underline">
                  进入 →
                </span>
              </button>
            );
          })}
        </div>

        <div className="pv-border p-6 text-[13.5px] text-black/70 leading-relaxed space-y-4">
          <div>
            <strong className="text-black">使用说明</strong>
          </div>
          <div>
            <strong>数据来源</strong>：本平台所有信息均来源于 PubMed 公开发表的<strong className="text-black">文献摘要</strong>，
            由人工标注与大模型自动抽取构建，研究方向为口服抗栓药物（阿哌沙班、华法林、利伐沙班、达比加群等）的药物警戒研究。
            所有结论仅反映文献所报告的研究结果，效应量（HR/RR/CI）为摘要报告值，未经统一校正。
          </div>
          <div>
            <strong>结果解读</strong>：关系索引的对比视图将同一药物对的证据按结局归并——降低风险记为优势、增加风险记为劣势，
            机制类关系不参与优劣判定；智能问答的每个结论附 PMID 引用，且引用已经过程序校验，确保来自本次检索结果。
          </div>
          <div>
            <strong>重要提示</strong>：本系统为方法学研究演示，
            <strong className="text-[var(--pv-bad)]">不构成任何用药建议、诊疗依据或监管决策依据</strong>，
            临床用药请遵循专业医师指导与药品说明书。
          </div>
        </div>
      </div>
    </div>
  );
}
