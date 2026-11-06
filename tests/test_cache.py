"""模型调用缓存：相同输入只调用一次。"""
from biolit.extract.cache import LLMCache


def test_set_and_get(tmp_path):
    cache = LLMCache(tmp_path / "cache.db")
    key = LLMCache.make_key("model", "system", "question")
    assert cache.get(key) is None
    cache.set(key, "model", "answer")
    assert cache.get(key) == "answer"


def test_any_change_gives_a_new_key():
    base = LLMCache.make_key("gemini-a", "system prompt", "question")
    assert base == LLMCache.make_key("gemini-a", "system prompt", "question")    # 同样的输入 → 同样的键
    assert base != LLMCache.make_key("gemini-b", "system prompt", "question")    # 换模型
    assert base != LLMCache.make_key("gemini-a", "system prompt v2", "question") # 改提示词
    assert base != LLMCache.make_key("gemini-a", "system prompt", "question?")   # 改问题


def test_separator_prevents_collisions():
    # 没有分隔符时 "ab"+"c" 和 "a"+"bc" 会拼成同一个字符串
    assert LLMCache.make_key("ab", "c") != LLMCache.make_key("a", "bc")


def test_cache_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "0")
    cache = LLMCache(tmp_path / "cache.db")
    cache.set("k", "model", "answer")
    assert cache.get("k") is None
    assert not (tmp_path / "cache.db").exists()
