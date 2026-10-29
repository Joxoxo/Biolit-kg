"""M3 第 3 步：证据核验 —— 检查模型给的证据句是否真的出自原文。

三种结果：
- verified    证据句在原文中逐字存在（忽略大小写和空格差异）
- approximate 原文中有一句和它高度相似（相似度 ≥ 0.9），可能是模型改了几个字
- unverified  原文里找不到相似的句子，可能是模型改写或编造的，需要人工核查
"""
import re
from difflib import SequenceMatcher


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _sentences(abstract: str) -> list[str]:
    # 按句号 / 问号 / 感叹号 + 空格切句；同时按换行切（结构化摘要每段一行）
    parts = re.split(r"(?<=[.!?])\s+|\n", abstract)
    return [_norm(p) for p in parts if p.strip()]


def check_evidence(evidence: str, source: str) -> tuple[str, float]:
    """source = 标题 + 摘要。"""
    ev, src = _norm(evidence), _norm(source)
    if ev and ev in src:
        return "verified", 1.0

    # 模型用 "[...]" 或 "..." 省略了中间部分：拆成几段，每段都在原文里 → 算"相似"
    fragments = [f.strip(" ,;") for f in re.split(r"\[\s*\.\.\.\s*\]|\.\.\.|…", ev)]
    fragments = [f for f in fragments if len(f) >= 15]
    if len(fragments) >= 2 and all(f in src for f in fragments):
        return "approximate", 0.95

    best = max((SequenceMatcher(None, ev, s).ratio() for s in _sentences(source)), default=0.0)
    return ("approximate" if best >= 0.9 else "unverified"), round(best, 3)
