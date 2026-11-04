export interface EffectSize {
  metric: string; // HR / RR / OR / WR
  v: number;
  lo: number;
  hi: number;
}

export interface Relation {
  pmid: string;
  study_type: string;
  subject: string;
  relation: string;
  object: string;
  comparator: string;
  effect: string;
  population: string;
  evidence: string;
  judgment: string; // 正确 | 部分正确 | 错误 | 漏抽
  note: string;
  batch: string; // v5 | holdout
  missed: boolean;
  eff: EffectSize | null;
}

export interface PvData {
  papers: Record<string, string>;
  relations: Relation[];
}

export type FilterState = {
  q: string;
  relations: Set<string>;
  onlyWithEff: boolean;
};
