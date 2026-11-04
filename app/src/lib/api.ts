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

export function extractText(payload: ExtractPayload) {
  return fetchJson<ExtractResult>("/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export interface GraphData {
  directed: boolean;
  multigraph: boolean;
  graph: Record<string, unknown>;
  nodes: { id: string; type: string; n_papers: number }[];
  links: {
    source: string;
    target: string;
    relations: {
      relation: string;
      comparator: string | null;
      n_papers: number;
      pmids: number[];
      study_types: Record<string, number>;
      evidence_score: number;
      example: { pmid: number; text: string } | null;
    }[];
  }[];
}

export function getGraph() {
  return fetchJson<GraphData>("/graph");
}

