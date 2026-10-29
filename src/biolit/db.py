"""数据库工具：连接 SQLite，并创建项目用到的表。

整个数据库就是一个文件：data/biolit.db

自测方法（在 biolit-kg 文件夹下）：
    python -m biolit.db
"""
import sqlite3
from pathlib import Path

# 项目根目录（biolit-kg/）：本文件位于 src/biolit/db.py，往上数 3 层
ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "biolit.db"

# 建表语句。IF NOT EXISTS：表已存在就跳过，所以可以放心重复运行
SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    pmid      INTEGER PRIMARY KEY,    -- PubMed 编号，主键 = 不允许重复
    title     TEXT,
    abstract  TEXT,
    year      INTEGER,
    journal   TEXT,
    source    TEXT DEFAULT 'pubmed',  -- 数据来源，以后还会有 'fda_label'
    added_at  TEXT DEFAULT CURRENT_TIMESTAMP  -- 入库时间，自动填写
);

-- 抽取记录：每篇文献 × 每个提示词版本 × 每个模型，一行
-- 同一篇文献可以用不同版本 / 不同模型各抽一次，方便第 8 天做对比
CREATE TABLE IF NOT EXISTS extractions (
    pmid            INTEGER,
    prompt_version  TEXT,
    model           TEXT,
    status          TEXT,     -- 'ok' 成功 / 'failed' 失败
    study_type      TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    seconds         REAL,
    raw_json        TEXT,     -- 模型返回的完整 JSON，留底备查
    error           TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pmid, prompt_version, model)   -- 联合主键：三者组合不能重复
);

CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pmid            INTEGER,
    prompt_version  TEXT,
    model           TEXT,
    name            TEXT,
    type            TEXT
);

CREATE TABLE IF NOT EXISTS relations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pmid            INTEGER,
    prompt_version  TEXT,
    model           TEXT,
    subject         TEXT,
    relation        TEXT,
    object          TEXT,
    comparator      TEXT,
    effect          TEXT,
    population      TEXT,
    evidence        TEXT
);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """打开数据库连接；数据库文件不存在时会自动创建，并建好表。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 查询结果可以按列名取值，如 row["title"]
    conn.executescript(SCHEMA)
    return conn


if __name__ == "__main__":
    # 自测：建库 → 插入一条假数据 → 查出来 → 删掉
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO papers (pmid, title, year, journal) VALUES (?, ?, ?, ?)",
        (1, "测试文献：warfarin and bleeding", 2024, "Test Journal"),
    )
    row = conn.execute("SELECT * FROM papers WHERE pmid = 1").fetchone()
    print("插入后查到：", dict(row))
    conn.execute("DELETE FROM papers WHERE pmid = 1")
    conn.commit()
    print("测试数据已删除。数据库位置：", DB_PATH)
    conn.close()
