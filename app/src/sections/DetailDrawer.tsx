import { useEffect, useRef } from "react";
import type { Relation } from "@/types/pv";

export function DetailDrawer({
  relation,
  papers,
  onClose,
}: {
  relation: Relation | null;
  papers: Record<string, string>;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [relation, onClose]);

  if (!relation) return null;

  const pubmed = `https://pubmed.ncbi.nlm.nih.gov/${relation.pmid}/`;

  return (
    <aside
      className="pv-border-l bg-white w-full lg:w-[400px] shrink-0 lg:overflow-y-auto lg:h-full pv-scroll"
      role="complementary"
      aria-label="关系详情"
    >
      <div className="p-4 space-y-5">
        {/* header */}
        <div className="flex items-start justify-between gap-3">
          <div className="pv-label pt-1">关系详情 · Detail</div>
          <button ref={closeRef} type="button" onClick={onClose} className="pv-chip" aria-label="关闭详情">
            关闭 ✕
          </button>
        </div>

        {/* title block */}
        <div>
          <div className="mono font-bold text-[19px] leading-snug break-words">{relation.subject}</div>
          <div className="inline-block my-1.5 px-2 py-0.5 pv-border text-[12px]">{relation.relation}</div>
          <div className="text-[15px] font-medium break-words">{relation.object}</div>
          {relation.comparator && (
            <div className="mono text-[12px] text-black/55 mt-1.5">vs {relation.comparator}</div>
          )}
        </div>

        {/* meta */}
        <dl className="pv-border divide-y divide-black/12 text-[12.5px]">
          {relation.population && <MetaRow k="人群" v={relation.population} />}
          {relation.effect && <MetaRow k="效果" v={relation.effect} mono />}
          {relation.study_type && relation.study_type !== "（漏抽）" && (
            <MetaRow k="研究类型" v={relation.study_type} />
          )}
          <div className="flex gap-3 px-3 py-2">
            <dt className="pv-label pt-0.5 shrink-0 w-14">PMID</dt>
            <dd>
              <a
                href={pubmed}
                target="_blank"
                rel="noreferrer"
                className="mono text-[12.5px] underline decoration-[var(--pv-accent)] decoration-2 underline-offset-2 hover:text-[var(--pv-accent)]"
              >
                {relation.pmid} ↗
              </a>
            </dd>
          </div>
        </dl>

        {/* evidence */}
        {relation.evidence && (
          <figure>
            <figcaption className="pv-label mb-2">证据句 · Evidence</figcaption>
            <blockquote className="pv-border-l-2 border-l-[3px] border-[var(--pv-accent)] pl-3 py-1 text-[13px] leading-relaxed text-black/80 italic">
              {relation.evidence}
            </blockquote>
          </figure>
        )}

        {/* note */}
        {relation.note && (
          <div>
            <div className="pv-label mb-2">备注 · Note</div>
            <p className="text-[12.5px] leading-relaxed text-black/70">{relation.note}</p>
          </div>
        )}

        {/* paper title */}
        {papers[relation.pmid] && (
          <div>
            <div className="pv-label mb-2">文献标题 · Title</div>
            <p className="text-[12.5px] leading-relaxed text-black/70">{papers[relation.pmid]}</p>
          </div>
        )}
      </div>
    </aside>
  );
}

function MetaRow({
  k, v, mono: isMono,
}: {
  k: string; v: string; mono?: boolean;
}) {
  return (
    <div className="flex gap-3 px-3 py-2">
      <dt className="pv-label pt-0.5 shrink-0 w-14">{k}</dt>
      <dd className={`break-words ${isMono ? "mono" : ""}`}>
        {v}
      </dd>
    </div>
  );
}
