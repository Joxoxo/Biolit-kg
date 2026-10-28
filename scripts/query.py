"""SQL 查询小工具：对项目数据库执行一条 SQL，并以表格形式显示结果。

用法（在 biolit-kg 文件夹下）：
    python scripts/query.py "SELECT COUNT(*) FROM papers"
"""
import sys

import pandas as pd

from biolit.db import get_connection

sql = sys.argv[1] if len(sys.argv) > 1 else "SELECT pmid, year, title FROM papers LIMIT 5"
pd.set_option("display.max_colwidth", 70)   # 长文本只显示前 70 个字符
pd.set_option("display.width", 200)
print(pd.read_sql_query(sql, get_connection()).to_string(index=False))
