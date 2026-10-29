"""M2 批量抽取：对数据库里所有还没抽取过的文献，逐篇调用大模型，结果存入数据库。

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.extract.run              # 全部未抽取的文献
    python -m biolit.extract.run --limit 20   # 只跑 20 篇（先小规模试跑）

特点：
- 断点续跑：已经抽取成功的（同一提示词版本 + 同一模型）自动跳过
- 控制速度：每次请求至少间隔 LLM_MIN_INTERVAL 秒（默认 5 秒，对应每分钟 12 次）
- 每日额度用完时保存进度并停止，第二天重新运行即可接着跑
- 单篇失败（如返回格式不合规）只记录错误，不影响其他文献
"""
import argparse
import os
import time

from biolit.db import get_connection
from biolit.extract.llm_client import DailyQuotaExceeded, GeminiClient
from biolit.extract.prompts import PROMPT_VERSION

MIN_INTERVAL = float(os.getenv("LLM_MIN_INTERVAL", "5"))


def save_result(conn, pmid, resp):
    """把一篇的抽取结果写入三张表。用 with conn 包起来 = 要么全部写入，要么全部不写（事务）。"""
    key = (pmid, PROMPT_VERSION, resp.model)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO extractions (pmid, prompt_version, model, status, study_type, "
            "input_tokens, output_tokens, seconds, raw_json) VALUES (?, ?, ?, 'ok', ?, ?, ?, ?, ?)",
            (*key, resp.result.study_type, resp.input_tokens, resp.output_tokens,
             resp.seconds, resp.result.model_dump_json()),
        )
        # 先删掉这篇的旧结果（如果之前失败重跑过），再插入新结果
        conn.execute("DELETE FROM entities WHERE pmid=? AND prompt_version=? AND model=?", key)
        conn.execute("DELETE FROM relations WHERE pmid=? AND prompt_version=? AND model=?", key)
        conn.executemany(
            "INSERT INTO entities (pmid, prompt_version, model, name, type) VALUES (?, ?, ?, ?, ?)",
            [(*key, e.name, e.type) for e in resp.result.entities],
        )
        conn.executemany(
            "INSERT INTO relations (pmid, prompt_version, model, subject, relation, object, "
            "comparator, effect, population, evidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(*key, r.subject, r.relation, r.object, r.comparator, r.effect, r.population, r.evidence)
             for r in resp.result.relations],
        )


def save_failure(conn, pmid, model, error):
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO extractions (pmid, prompt_version, model, status, error) "
            "VALUES (?, ?, ?, 'failed', ?)",
            (pmid, PROMPT_VERSION, model, str(error)[:500]),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少篇")
    args = parser.parse_args()

    conn = get_connection()
    client = GeminiClient()

    # 找出还没有成功抽取过的文献（失败的会重新尝试）
    todo = conn.execute(
        """SELECT p.pmid, p.title, p.abstract FROM papers p
           WHERE NOT EXISTS (
               SELECT 1 FROM extractions e
               WHERE e.pmid = p.pmid AND e.prompt_version = ? AND e.model = ? AND e.status = 'ok')
           ORDER BY p.pmid""",
        (PROMPT_VERSION, client.model),
    ).fetchall()
    if args.limit:
        todo = todo[:args.limit]

    print(f"提示词 {PROMPT_VERSION} | 模型 {client.model} | 待抽取 {len(todo)} 篇 | "
          f"间隔 {MIN_INTERVAL} 秒，预计约 {len(todo) * MIN_INTERVAL / 60:.0f} 分钟\n")

    ok = failed = 0
    for i, paper in enumerate(todo, 1):
        start = time.time()
        try:
            resp = client.extract(paper["title"], paper["abstract"])
            save_result(conn, paper["pmid"], resp)
            ok += 1
            print(f"[{i}/{len(todo)}] PMID {paper['pmid']} ✓ {resp.result.study_type:<13} "
                  f"{len(resp.result.entities):>2} 实体 {len(resp.result.relations):>2} 关系 "
                  f"({resp.seconds}s)")
        except DailyQuotaExceeded:
            print(f"\n今天的额度用完了。已完成 {ok} 篇，进度已保存；明天重新运行同一条命令即可继续。")
            break
        except Exception as e:   # 单篇出错：记下来，继续下一篇
            failed += 1
            save_failure(conn, paper["pmid"], client.model, e)
            print(f"[{i}/{len(todo)}] PMID {paper['pmid']} ✗ 失败：{str(e)[:100]}")

        # 控制速度：如果这次用时不到 MIN_INTERVAL 秒，就补足等待时间
        time.sleep(max(0, MIN_INTERVAL - (time.time() - start)))

    total_ok = conn.execute(
        "SELECT COUNT(*) FROM extractions WHERE prompt_version=? AND model=? AND status='ok'",
        (PROMPT_VERSION, client.model),
    ).fetchone()[0]
    print(f"\n本次：成功 {ok} 篇，失败 {failed} 篇。累计已抽取 {total_ok} 篇。")


if __name__ == "__main__":
    main()
