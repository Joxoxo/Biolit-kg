"""M5 第 1 步（下）：给所有文献建立向量索引。

做法：每篇文献的"标题 + 摘要"转成一个向量，所有向量存成一个矩阵（994 行 × 768 列）。
存储：用 numpy 的 .npz 文件，不需要额外的向量数据库 —— 1000 篇的规模，numpy 计算相似度不到 0.1 秒。
支持增量：已经建过索引的文献会跳过，新增文献只转换新的部分。

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.rag.index
"""
import time

import numpy as np

from biolit.db import ROOT, get_connection
from biolit.rag.embed import DIM, EMBED_MODEL, Embedder

INDEX_PATH = ROOT / "data" / "processed" / "index.npz"


def doc_text(title: str, abstract: str) -> str:
    return f"{title}\n\n{abstract}"


def load_index():
    """返回 (pmids 数组, 向量矩阵)；索引不存在时返回空。"""
    if not INDEX_PATH.exists():
        return np.array([], dtype=np.int64), np.zeros((0, DIM), dtype=np.float32)
    data = np.load(INDEX_PATH)
    return data["pmids"], data["vectors"]


def build_index():
    conn = get_connection()
    old_pmids, old_vecs = load_index()
    done = set(old_pmids.tolist())

    papers = [p for p in conn.execute("SELECT pmid, title, abstract FROM papers ORDER BY pmid")
              if p["pmid"] not in done]
    print(f"向量模型 {EMBED_MODEL}（{DIM} 维）| 已有索引 {len(done)} 篇，需新增 {len(papers)} 篇")
    if not papers:
        return

    start = time.time()
    vecs = Embedder().embed([doc_text(p["title"], p["abstract"]) for p in papers], "RETRIEVAL_DOCUMENT")
    pmids = np.concatenate([old_pmids, np.array([p["pmid"] for p in papers], dtype=np.int64)])
    vectors = np.vstack([old_vecs, vecs])
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez(INDEX_PATH, pmids=pmids, vectors=vectors)
    print(f"完成：索引共 {len(pmids)} 篇，矩阵形状 {vectors.shape}，用时 {time.time() - start:.0f} 秒")


def demo_search(question: str, k: int = 5):
    """演示向量检索的核心：问题向量 × 文献向量矩阵 = 每篇文献的相似度，取最高的 k 篇。"""
    pmids, vectors = load_index()
    q = Embedder().embed([question], "RETRIEVAL_QUERY")[0]
    scores = vectors @ q                       # 矩阵乘法：一次算出和所有文献的相似度
    top = np.argsort(-scores)[:k]              # 从高到低排序，取前 k 个
    conn = get_connection()
    print(f"\n问题：{question}")
    for i in top:
        title = conn.execute("SELECT title FROM papers WHERE pmid=?", (int(pmids[i]),)).fetchone()["title"]
        print(f"  {scores[i]:.3f}  PMID {pmids[i]}  {title[:90]}")


if __name__ == "__main__":
    build_index()
    # 用中文提问，看能否检索到英文文献
    demo_search("阿哌沙班和华法林相比，大出血风险怎么样？")
    demo_search("哪些药物会通过 CYP3A4 影响替格瑞洛的血药浓度？")
