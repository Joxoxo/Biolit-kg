"""M3 第 3 步：证据核验 —— 检查模型给的证据句是否真的出自原文。

三种结果：
- verified    证据句在原文中逐字存在（忽略大小写、空格和常见符号写法差异）
- approximate 证据句的绝大部分（≥ 90%）能在原文中按顺序找到，可能被模型改了几个字或省略了一段
- unverified  原文里找不到，可能是模型改写或编造的，需要人工核查

v2 修正（2026-11）：之前会把这些情况误判为 unverified ——
  · 模型把特殊符号换成了普通字符（≤ → <=，μM → uM）
  · 原文句号后漏了空格（如 "CYP2D6.CC-90001"），导致切句出错
现在先统一符号写法，再用"覆盖率"代替"逐句比对"，不再依赖切句。
另外单独核对数字：覆盖率对"改了一个数字"不敏感（如把 p = 0.031 抄成 0.398，其余文字都对），
而数字恰恰最关键，所以证据句里出现原文没有的数字，一律判 unverified。
"""
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

# 常见的符号变体：统一成最普通的写法
SYMBOLS = {"≤": "<=", "≥": ">=", "μ": "u", "µ": "u", "–": "-", "—": "-", "−": "-", "‐": "-",
           "×": "x", "·": ".", "’": "'", "‘": "'", "“": '"', "”": '"'}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)      # 全角 / 特殊空格等统一成标准形式
    for a, b in SYMBOLS.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().lower()


def _coverage(ev: str, src: str) -> float:
    """证据句中有多大比例的字符，能在原文里按顺序找到（不要求连续，所以能容忍少量改字和省略）。"""
    blocks = SequenceMatcher(None, ev, src, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks if b.size >= 4) / max(len(ev), 1)   # 忽略 4 个字符以下的零碎匹配


NUM = re.compile(r"\d+(?:\.\d+)?")


def check_evidence(evidence: str, source: str) -> tuple[str, float]:
    """source = 标题 + 摘要。"""
    ev, src = _norm(evidence), _norm(source)
    if ev and ev in src:
        return "verified", 1.0
    score = round(_coverage(ev, src), 3)
    # 按"多重集合"比较：证据里某个数字出现的次数，不能多于原文
    # （p = 0.398 在原文出现 1 次，证据句里却出现 2 次 → 有一处是抄错的）
    if Counter(NUM.findall(ev)) - Counter(NUM.findall(src)):
        return "unverified", score            # 出现了原文没有的数字：可能抄错或编造
    return ("approximate" if score >= 0.9 else "unverified"), score
