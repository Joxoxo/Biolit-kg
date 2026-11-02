"""M5 第 2 步：混合检索 = 理解问题 + 向量检索 + 实体匹配 + 知识图谱。

为什么不只用向量检索：
向量擅长抓"主题"（抗凝药 + 出血），但分不清"具体哪个药"——
问"阿哌沙班 vs 华法林"，也会搜出"利伐沙班 vs 阿司匹林"，而且分数几乎一样。
所以再加一路"实体匹配"：文献里抽出的实体和问题里的实体重合越多，排名越靠前。

流程：
  ① 理解问题：大模型把中文问题转成英文检索句 + 实体列表，再经过同义词表标准化
  ② 向量检索：取相似度最高的 50 篇作为候选
  ③ 重新排序：最终分 = 向量相似度 + 0.05 × 实体匹配度
     （候选文献的向量分通常只差 0.01–0.05，所以 0.05 的加分足以让"药名对得上"的文献排到前面，
       同时向量分仍然起作用）
  ④ 查知识图谱：问题里实体之间的关系统计（如"52 篇文献支持阿哌沙班相比华法林大出血更少"）

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.rag.retrieve
"""
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel, Field

from biolit.db import ACTIVE_VERSION, get_connection
from biolit.extract.llm_client import GeminiClient
from biolit.graph.build import GRAPH_PATH, load_graph
from biolit.normalize.synonyms import Normalizer
from biolit.rag.embed import Embedder
from biolit.rag.index import load_index

N_CANDIDATES = 50     # 向量检索先取多少篇候选
ENTITY_BONUS = 0.05   # 问题里的实体全部匹配时的加分
PK_RELATIONS = {"interacts_with", "inhibits", "induces", "metabolized_by"}   # 药代 / 相互作用类关系


# ---------- ① 理解问题 ----------

class QueryInfo(BaseModel):
    english_query: str = Field(description="把问题翻译成英文的检索句，保留所有医学术语")
    entities: list[str] = Field(description="问题中的医学实体（药物、不良事件、结局、酶、疾病），用英文通用名")


QUERY_PROMPT = """You convert a user's question about oral antithrombotic drugs into a search query.
Return:
- english_query: the question rewritten in English for searching biomedical abstracts.
- entities: the medical entities mentioned, in standard English names
  (e.g. 阿哌沙班 -> apixaban, 华法林 -> warfarin, 大出血 -> major bleeding, 新型口服抗凝药 -> DOAC).
Only list entities that are actually in the question."""


@dataclass
class Paper:
    pmid: int
    title: str
    abstract: str
    year: int | None
    journal: str
    study_type: str | None
    vector_score: float
    entity_match: float
    matched: list[str]
    score: float = 0.0


@dataclass
class RetrievalResult:
    question: str
    query: QueryInfo
    entities_norm: list[str]
    papers: list[Paper]
    graph_facts: list[dict] = field(default_factory=list)


class Retriever:
    def __init__(self):
        self.conn = get_connection()
        self.llm = GeminiClient()
        self.embedder = Embedder()
        self.norm = Normalizer()
        self.pmids, self.vectors = load_index()
        self.graph = load_graph() if GRAPH_PATH.exists() else None

        # 每篇文献里出现过哪些（标准化后的）实体，事先读进内存
        self.paper_entities = defaultdict(set)
        for r in self.conn.execute("SELECT pmid, name_norm FROM entities WHERE name_norm IS NOT NULL "
                                   "AND prompt_version = ?", (ACTIVE_VERSION,)):
            self.paper_entities[r["pmid"]].add(r["name_norm"])
        for r in self.conn.execute("SELECT pmid, subject_norm, object_norm FROM relations "
                                   "WHERE prompt_version = ?", (ACTIVE_VERSION,)):
            self.paper_entities[r["pmid"]].update(x for x in (r["subject_norm"], r["object_norm"]) if x)

        # 上下级关系反过来查："doac" 的子类有 apixaban、rivaroxaban……
        self.children = defaultdict(set)
        for child, parents in self.norm.hierarchy.items():
            for p in parents:
                self.children[p].add(child)

    def _expand(self, entity: str) -> set[str]:
        """一个实体 + 它所有的子类。问 DOAC 时，提到 apixaban 的文献也算匹配。"""
        out, stack = {entity}, [entity]
        while stack:
            for c in self.children.get(stack.pop(), ()):
                if c not in out:
                    out.add(c)
                    stack.append(c)
        return out

    def retrieve(self, question: str, k: int = 5) -> RetrievalResult:
        # ① 理解问题
        q: QueryInfo = self.llm.generate(question, QUERY_PROMPT, schema=QueryInfo)
        ents = list(dict.fromkeys(self.norm(e) for e in q.entities if self.norm(e)))

        # ② 向量检索：用英文检索句（和英文文献更匹配）
        qvec = self.embedder.embed([q.english_query], "RETRIEVAL_QUERY")[0]
        sims = self.vectors @ qvec
        top = np.argsort(-sims)[:N_CANDIDATES]

        # ③ 重新排序
        papers = []
        for i in top:
            pmid = int(self.pmids[i])
            have = self.paper_entities.get(pmid, set())
            matched = [e for e in ents if self._expand(e) & have]
            row = self.conn.execute(
                "SELECT p.title, p.abstract, p.year, p.journal, e.study_type FROM papers p "
                "LEFT JOIN extractions e ON e.pmid = p.pmid AND e.status = 'ok' AND e.prompt_version = ? "
                "WHERE p.pmid = ?", (ACTIVE_VERSION, pmid)).fetchone()
            ent_score = len(matched) / len(ents) if ents else 0.0
            papers.append(Paper(pmid, row["title"], row["abstract"], row["year"], row["journal"],
                                row["study_type"], float(sims[i]), ent_score, matched,
                                score=float(sims[i]) + ENTITY_BONUS * ent_score))
        papers.sort(key=lambda p: -p.score)

        # ④ 知识图谱
        facts = self.graph_facts(ents) if self.graph is not None else []
        return RetrievalResult(question, q, ents, papers[:k], facts)

    def graph_facts(self, ents: list[str], limit: int = 15) -> list[dict]:
        """从图谱里找和问题实体相关的关系，按相关程度排序：
        优先级 2：关系两端（或对照药）都是问题里的实体，如 apixaban → major bleeding（对照 warfarin）
        优先级 1：一端是问题实体，且是相互作用 / 代谢类关系，如 resveratrol → interacts_with → ticagrelor
        """
        G, facts = self.graph, {}
        ent_set = set(ents)
        for a in ents:
            if a not in G:
                continue
            neighbors = [(a, b) for b in G.successors(a)] + [(b, a) for b in G.predecessors(a)]
            for s, o in neighbors:
                for r in G[s][o]["relations"]:
                    other = o if s == a else s
                    if other in ent_set or r["comparator"] in ent_set:
                        prio = 2
                    elif r["relation"] == "metabolized_by" and s not in ent_set:
                        continue   # "别的药也被 CYP3A4 代谢"对回答问题帮助不大
                    elif r["relation"] in PK_RELATIONS or len(ents) == 1:
                        prio = 1
                    else:
                        continue
                    key = (s, r["relation"], o, r["comparator"])
                    facts[key] = {"subject": s, "object": o, "priority": prio, **r}
        # 排序：优先级 → 文献数 → 相互作用类排在"被代谢"前面
        return sorted(facts.values(), key=lambda f: (-f["priority"], -f["n_papers"],
                                                     f["relation"] == "metabolized_by"))[:limit]


def show(res: RetrievalResult):
    print(f"\n问题：{res.question}")
    print(f"英文检索句：{res.query.english_query}")
    print(f"识别出的实体：{res.entities_norm}")
    print("\n检索结果（综合分 = 向量 + 实体匹配）：")
    for p in res.papers:
        print(f"  {p.score:.3f}（向量 {p.vector_score:.3f}，匹配 {p.matched}）PMID {p.pmid} [{p.study_type}]"
              f"  {p.title[:70]}")
    if res.graph_facts:
        print("\n知识图谱中的相关结论：")
        for f in res.graph_facts:
            cmp = f"（对照 {f['comparator']}）" if f["comparator"] else ""
            print(f"  {f['subject']} --{f['relation']}--> {f['object']}{cmp}  [{f['n_papers']} 篇]")


if __name__ == "__main__":
    r = Retriever()
    show(r.retrieve("阿哌沙班和华法林相比，大出血风险怎么样？"))
    show(r.retrieve("哪些药物会通过 CYP3A4 影响替格瑞洛的血药浓度？"))
