"""GraphRAG 的图谱查询：给定问题里的实体，从图谱中找出相关结论并排序。"""
import networkx as nx

from biolit.rag.retrieve import Retriever


def rel(relation, n, comparator=None):
    return {"relation": relation, "comparator": comparator, "n_papers": n, "pmids": [], "study_types": {}}


def make_retriever():
    G = nx.DiGraph()
    G.add_edge("apixaban", "major bleeding", relations=[rel("decreases_risk", 52, "warfarin"),
                                                        rel("decreases_risk", 30, "rivaroxaban")])
    G.add_edge("apixaban", "cyp3a4", relations=[rel("metabolized_by", 7)])
    G.add_edge("clarithromycin", "apixaban", relations=[rel("interacts_with", 2)])
    G.add_edge("rivaroxaban", "cyp3a4", relations=[rel("metabolized_by", 8)])
    r = object.__new__(Retriever)      # 跳过 __init__：不加载向量索引、不连模型
    r.graph = G
    return r


def test_both_entities_in_question_rank_first():
    facts = make_retriever().graph_facts(["apixaban", "warfarin"])
    top = facts[0]
    assert (top["subject"], top["object"], top["comparator"]) == ("apixaban", "major bleeding", "warfarin")
    assert top["priority"] == 2


def test_interaction_is_included_for_single_entity():
    facts = make_retriever().graph_facts(["apixaban"])
    assert any(f["subject"] == "clarithromycin" and f["relation"] == "interacts_with" for f in facts)


def test_other_drugs_metabolized_by_same_enzyme_are_skipped():
    # 问 CYP3A4 时，"利伐沙班也被 CYP3A4 代谢"对回答帮助不大，不应出现
    facts = make_retriever().graph_facts(["cyp3a4", "apixaban"])
    assert all(f["subject"] != "rivaroxaban" for f in facts)


def test_unknown_entity_returns_nothing():
    assert make_retriever().graph_facts(["heparin"]) == []
