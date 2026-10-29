"""M3 主流程：标准化实体名 + 证据核验，结果写回数据库的新字段（原始字段保持不动）。

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.normalize.run

改了 configs/synonyms.yaml 之后重新运行一次即可，结果会整体刷新。
"""
from collections import Counter

from biolit.db import get_connection
from biolit.normalize.evidence import check_evidence
from biolit.normalize.synonyms import Normalizer

NEW_COLUMNS = {
    "entities": ["name_norm TEXT"],
    "relations": ["subject_norm TEXT", "object_norm TEXT", "comparator_norm TEXT",
                  "evidence_status TEXT", "evidence_score REAL"],
}


def add_columns(conn):
    """给已有的表加新列。SQLite 没有 'ADD COLUMN IF NOT EXISTS'，所以先查已有哪些列。"""
    for table, cols in NEW_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for col in cols:
            if col.split()[0] not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")


def main():
    conn = get_connection()
    add_columns(conn)
    norm = Normalizer()

    # ---------- 实体标准化 ----------
    ents = conn.execute("SELECT id, name FROM entities").fetchall()
    with conn:
        conn.executemany("UPDATE entities SET name_norm=? WHERE id=?",
                         [(norm(e["name"]), e["id"]) for e in ents])
    before = len({e["name"] for e in ents})
    after = conn.execute("SELECT COUNT(DISTINCT name_norm) FROM entities").fetchone()[0]
    print(f"实体写法：{before} 种 → 标准化后 {after} 种")

    # ---------- 关系标准化 + 证据核验 ----------
    rels = conn.execute(
        "SELECT r.id, r.subject, r.object, r.comparator, r.evidence, p.title, p.abstract "
        "FROM relations r JOIN papers p ON p.pmid = r.pmid").fetchall()
    updates, status_count = [], Counter()
    for r in rels:
        status, score = check_evidence(r["evidence"], f"{r['title']}\n{r['abstract']}")
        status_count[status] += 1
        updates.append((norm(r["subject"]), norm(r["object"]), norm(r["comparator"]),
                        status, score, r["id"]))
    with conn:
        conn.executemany(
            "UPDATE relations SET subject_norm=?, object_norm=?, comparator_norm=?, "
            "evidence_status=?, evidence_score=? WHERE id=?", updates)

    print(f"\n证据核验（共 {len(rels)} 条关系）：")
    for s in ["verified", "approximate", "unverified"]:
        print(f"  {s:<12} {status_count[s]:>5}  ({status_count[s] / len(rels):.1%})")

    # ---------- 上下级关系表 ----------
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS entity_hierarchy (child TEXT, parent TEXT)")
        conn.execute("DELETE FROM entity_hierarchy")
        conn.executemany("INSERT INTO entity_hierarchy VALUES (?, ?)",
                         [(c, p) for c, ps in norm.hierarchy.items() for p in ps])
    print(f"\n上下级关系：{sum(len(v) for v in norm.hierarchy.values())} 条")

    # ---------- 还没被同义词表覆盖的高频写法（方便以后补充） ----------
    print("\n出现 ≥ 5 次、但不在同义词表里的写法（可考虑补充）：")
    rows = conn.execute(
        "SELECT name_norm, COUNT(*) AS n FROM entities GROUP BY name_norm HAVING n >= 5 "
        "ORDER BY n DESC").fetchall()
    known = set(norm.lookup.values())
    print("  " + "; ".join(f"{r['name_norm']}({r['n']})" for r in rows if r["name_norm"] not in known))
    conn.close()


if __name__ == "__main__":
    main()
