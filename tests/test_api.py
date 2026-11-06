"""FastAPI 接口：用假的问答对象代替真模型，不调用 Gemini、不消耗额度。"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import biolit.api.main as api
from biolit.extract.llm_client import CACHE_ONLY, CacheMiss, DailyQuotaExceeded


class FakeQA:
    llm = SimpleNamespace(calls=0)

    def ask(self, question, k=5):
        paper = SimpleNamespace(pmid=123, title="A trial", year=2024, journal="J", study_type="rct",
                                score=0.81234, matched=["apixaban"])
        return SimpleNamespace(question=question, text="结论 [PMID:123]", cited=[123], invalid_citations=[],
                               retrieval=SimpleNamespace(papers=[paper], graph_facts=[]))


class QuotaQA:
    llm = SimpleNamespace(calls=0)

    def ask(self, question, k=5):
        raise DailyQuotaExceeded("PerDay")


class CacheOnlyQA:
    """模拟只读缓存模式：开关打开时，没缓存的问题会抛 CacheMiss。"""
    llm = SimpleNamespace(calls=0)

    def ask(self, question, k=5):
        if CACHE_ONLY.get():
            raise CacheMiss()
        return FakeQA().ask(question)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "_qa", None)
    api._recent.clear()                                  # 每个测试重新计算访问频率
    api._usage.update(calls=0)
    api._extract_usage.update(total=0)
    api._extract_usage["by_ip"].clear()
    return TestClient(api.app)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_ask_returns_answer_and_citations(client, monkeypatch):
    monkeypatch.setattr(api, "get_qa", lambda: FakeQA())
    data = client.post("/api/ask", json={"question": "阿哌沙班出血风险？"}).json()
    assert data["answer"] == "结论 [PMID:123]"
    assert data["cited"] == [123]
    assert data["papers"][0]["score"] == 0.8123          # 分数保留 4 位小数


def test_ask_rejects_empty_question(client):
    assert client.post("/api/ask", json={"question": ""}).status_code == 422


def test_quota_exceeded_returns_429(client, monkeypatch):
    monkeypatch.setattr(api, "get_qa", lambda: QuotaQA())
    assert client.post("/api/ask", json={"question": "x"}).status_code == 429


def test_graph_missing_returns_503(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "GRAPH_PATH", tmp_path / "none.json")
    assert client.get("/api/graph").status_code == 503


def test_rate_limit_per_visitor(client, monkeypatch):
    monkeypatch.setattr(api, "get_qa", lambda: FakeQA())
    codes = [client.post("/api/ask", json={"question": "x"}).status_code for _ in range(api.RATE_PER_MIN + 1)]
    assert codes[:-1] == [200] * api.RATE_PER_MIN
    assert codes[-1] == 429


def test_daily_budget_switches_to_cache_only(client, monkeypatch):
    monkeypatch.setattr(api, "get_qa", lambda: CacheOnlyQA())
    assert client.post("/api/ask", json={"question": "x"}).status_code == 200
    api._usage.update(calls=api.DAILY_CALLS)            # 假装今天的额度用完了
    r = client.post("/api/ask", json={"question": "x"})
    assert r.status_code == 429
    assert "示例问题" in r.json()["detail"]


def test_profile_unknown_drug_returns_404(client):
    assert client.get("/api/profile/heparin").status_code == 404


def test_drug_list(client):
    ids = [d["id"] for d in client.get("/api/drugs").json()]
    assert "apixaban" in ids and len(ids) == 7


class FakeExtractor:
    """模拟抽取：缓存里只有"示例"这篇；只读缓存模式下，其他摘要会抛 CacheMiss。"""
    def __init__(self):
        self.calls = 0

    def extract(self, title, abstract):
        if title != "示例":
            if CACHE_ONLY.get():
                raise CacheMiss()
            self.calls += 1
        return SimpleNamespace(result=SimpleNamespace(study_type="rct", entities=[], relations=[]),
                               model="m", input_tokens=1, output_tokens=1, seconds=0.1)


def test_extract_limit_per_visitor(client, monkeypatch):
    fake = FakeExtractor()
    monkeypatch.setattr(api, "get_client", lambda: fake)
    monkeypatch.setattr(api, "RATE_PER_MIN", 100)       # 只测每日次数，不让每分钟限流干扰
    codes = [client.post("/api/extract", json={"title": f"t{i}", "abstract": "a"}).status_code
             for i in range(api.EXTRACT_PER_IP + 1)]
    assert codes == [200] * api.EXTRACT_PER_IP + [429]
    # 次数用完后，已缓存的示例摘要仍然可以用
    assert client.post("/api/extract", json={"title": "示例", "abstract": "a"}).status_code == 200


def test_extract_rejects_full_text(client):
    assert client.post("/api/extract", json={"title": "t", "abstract": "x" * 7000}).status_code == 422
