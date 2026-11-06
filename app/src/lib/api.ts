const API_PREFIX = "/api";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_PREFIX}${path}`, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data?.detail || `${res.status} ${res.statusText}`;
    throw new Error(msg);
  }
  return data as T;
}

export function getHealth() {
  return fetchJson<{ status: string }>("/health");
}

export interface AskPayload {
  question: string;
  k?: number;
}

export interface AskResult {
  question: string;
  answer: string;
  cited: number[];
  invalid_citations: number[];
  papers: {
    pmid: number;
    title: string;
    year: number | null;
    journal: string;
    study_type: string | null;
    score: number;
    matched: string[];
  }[];
  graph_facts: {
    subject: string;
    object: string;
    relation: string;
    comparator: string | null;
    n_papers: number;
    study_types: Record<string, number>;
    priority: number;
  }[];
}

export function askQuestion(payload: AskPayload) {
  return fetchJson<AskResult>("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export interface ExtractPayload {
  title: string;
  abstract: string;
}

export interface ExtractResult {
  study_type: string;
  entities: { name: string; type: string }[];
  relations: {
    subject: string;
    relation: string;
    object: string;
    comparator: string | null;
    effect: string | null;
    population: string | null;
    evidence: string;
  }[];
  model: string;
  input_tokens: number;
  output_tokens: number;
  seconds: number;
}

export function getExtractExample() {
  return fetchJson<{ pmid: number; title: string; abstract: string; limit_per_day: number }>("/extract/example");
}

export function extractText(payload: ExtractPayload) {
  return fetchJson<ExtractResult>("/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ---------- 药物安全档案 ----------

export interface DrugOption {
  id: string;
  zh: string;
}

export interface Comparison {
  comparator: string;            // 空字符串 = 文献未指明对照
  outcome: string;
  outcome_type: string;
  direction: "decreases" | "increases" | "mixed";
  n_dec: number;
  n_inc: number;
  n_papers: number;
  pmids: number[];
  study_types: Record<string, number>;
  example: { pmid: number; text: string } | null;
}

export interface Mechanism {
  partner: string;
  partner_type: string;
  relations: string[];
  direction: "in" | "out" | "";
  n_papers: number;
  pmids: number[];
  example: { pmid: number; text: string } | null;
  label_status: string | null;   // 说明书比对结果
  label_evidence: string | null;
  review: string | null;         // 人工审核：真信号 / 说明书其实有 / 抽取错误
  review_note: string | null;
}

export interface DrugProfile {
  drug: string;
  drug_zh: string;
  n_papers: number;
  n_comparisons: number;
  n_conflicts: number;
  n_signals: number;
  comparisons: Comparison[];
  mechanisms: Mechanism[];
}

export interface EvidencePaper {
  pmid: number;
  title: string;
  year: number | null;
  journal: string;
  study_type: string | null;
  sentences: string[];
}

export function getDrugs() {
  return fetchJson<DrugOption[]>("/drugs");
}

export function getProfile(drug: string) {
  return fetchJson<DrugProfile>(`/profile/${encodeURIComponent(drug)}`);
}

export function getEvidence(pmids: number[], a: string, b: string) {
  const q = new URLSearchParams({ pmids: pmids.slice(0, 20).join(","), a, b });
  return fetchJson<EvidencePaper[]>(`/evidence?${q}`);
}
