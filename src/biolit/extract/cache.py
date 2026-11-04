"""模型调用缓存：相同的输入（模型 + 系统提示词 + 内容 + 输出格式）只真正调用一次，结果存进本地 SQLite。

为什么需要：
1. 省额度：调试评估脚本时反复重跑，已经问过的不会再消耗免费额度
2. 可复现：同一个问题每次拿到同一个答案，评估结果不会因为模型的随机性而波动

缓存文件：data/processed/llm_cache.db（已被 .gitignore 的 *.db 规则排除，不会提交）
关闭缓存：在 .env 里加一行 LLM_CACHE=0
"""
import hashlib
import os
import sqlite3
import threading
import time

from biolit.db import ROOT

CACHE_PATH = ROOT / "data" / "processed" / "llm_cache.db"


class LLMCache:
    def __init__(self, path=CACHE_PATH):
        self.enabled = os.getenv("LLM_CACHE", "1") != "0"
        if not self.enabled:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()        # 网页后端可能多个请求同时写，加锁避免冲突
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS cache ("
                          "key TEXT PRIMARY KEY, model TEXT, output TEXT, created REAL)")

    @staticmethod
    def make_key(*parts) -> str:
        """把所有输入拼起来算一个哈希值。任何一部分变了（比如改了提示词），哈希就变，自动不命中旧缓存。"""
        h = hashlib.sha256()
        for p in parts:
            h.update(str(p).encode("utf-8"))
            h.update(b"\x00")               # 分隔符，避免 "ab"+"c" 和 "a"+"bc" 撞车
        return h.hexdigest()

    def get(self, key: str) -> str | None:
        if not self.enabled:
            return None
        with self.lock:
            row = self.conn.execute("SELECT output FROM cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key: str, model: str, output: str):
        if not self.enabled:
            return
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?)",
                              (key, model, output, time.time()))
            self.conn.commit()
