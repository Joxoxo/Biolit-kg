"""M5 第 1 步（上）：把文字转换成向量（embedding）。

什么是向量：一串数字（这里是 768 个），代表一段文字的"意思"。
意思越接近的两段文字，它们的向量在空间中的方向越接近。
所以"阿哌沙班出血风险"和 "apixaban bleeding risk" 虽然语言不同，向量却很接近 —— 这就是跨语言检索的原理。
"""
import os
import time

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from biolit.db import ROOT

load_dotenv(ROOT / ".env")

EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
DIM = 768          # 向量维度：模型最大支持 3072，768 已经够用，且存储小、计算快
BATCH = 50         # 每次请求最多转换多少段文字


class Embedder:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def embed(self, texts: list[str], task: str) -> np.ndarray:
        """task:
        - "RETRIEVAL_DOCUMENT"：给文献建索引时用
        - "RETRIEVAL_QUERY"   ：给用户问题转向量时用
        同一个模型针对"文档"和"问题"做了不同优化，检索效果更好。
        """
        vectors = []
        for i in range(0, len(texts), BATCH):
            batch = texts[i:i + BATCH]
            vectors.extend(self._call(batch, task))
            if len(texts) > BATCH:
                print(f"  已转换 {min(i + BATCH, len(texts))}/{len(texts)}")
        arr = np.array(vectors, dtype=np.float32)
        # 归一化：把每个向量的长度变成 1，之后"余弦相似度"就等于简单的点积
        return arr / np.linalg.norm(arr, axis=1, keepdims=True)

    def _call(self, batch, task, max_retries=5):
        for attempt in range(1, max_retries + 1):
            try:
                result = self.client.models.embed_content(
                    model=EMBED_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type=task, output_dimensionality=DIM),
                )
                return [e.values for e in result.embeddings]
            except errors.APIError as e:
                if e.code not in {429, 500, 503} or attempt == max_retries:
                    raise
                wait = 10 * attempt
                print(f"  [{e.code}] 稍后重试，等待 {wait} 秒…")
                time.sleep(wait)
