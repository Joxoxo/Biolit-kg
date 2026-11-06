"""药物安全档案：比较结论的视角转换和"结论不一致"判断。"""
import json

import biolit.api.profile as profile


def rel(relation, comparator, pmids):
    return {"relation": relation, "comparator": comparator, "n_papers": len(pmids), "pmids": pmids,
            "study_types": {"observational": len(pmids)}, "example": None}


def use_graph(monkeypatch, tmp_path, links):
    path = tmp_path / "graph.json"
    nodes = [{"id": x, "type": "drug", "n_papers": 1} for x in ("apixaban", "warfarin", "clarithromycin")]
    nodes += [{"id": "major bleeding", "type": "adverse_event", "n_papers": 1}]
    path.write_text(json.dumps({"nodes": nodes, "links": links}), encoding="utf-8")
    monkeypatch.setattr(profile, "GRAPH_PATH", path)
    monkeypatch.setattr(profile, "CROSSCHECK", tmp_path / "none.json")
    profile._load.cache_clear()


def test_flipped_relation_is_merged(monkeypatch, tmp_path):
    # "华法林相比阿哌沙班增加大出血" = "阿哌沙班相比华法林降低大出血"，两篇应合并成一行
    use_graph(monkeypatch, tmp_path, [
        {"source": "apixaban", "target": "major bleeding", "relations": [rel("decreases_risk", "warfarin", [1])]},
        {"source": "warfarin", "target": "major bleeding", "relations": [rel("increases_risk", "apixaban", [2])]},
    ])
    rows = profile.build_profile("apixaban")["comparisons"]
    assert len(rows) == 1
    assert (rows[0]["comparator"], rows[0]["n_dec"], rows[0]["n_inc"]) == ("warfarin", 2, 0)


def test_conflict_needs_two_papers_on_minority_side(monkeypatch, tmp_path):
    use_graph(monkeypatch, tmp_path, [
        {"source": "apixaban", "target": "major bleeding", "relations": [
            rel("decreases_risk", "warfarin", [1, 2, 3]), rel("increases_risk", "warfarin", [4])]},
    ])
    assert profile.build_profile("apixaban")["comparisons"][0]["direction"] == "decreases"   # 只有 1 篇相反
    use_graph(monkeypatch, tmp_path, [
        {"source": "apixaban", "target": "major bleeding", "relations": [
            rel("decreases_risk", "warfarin", [1, 2, 3]), rel("increases_risk", "warfarin", [4, 5])]},
    ])
    p = profile.build_profile("apixaban")
    assert p["comparisons"][0]["direction"] == "mixed" and p["n_conflicts"] == 1
