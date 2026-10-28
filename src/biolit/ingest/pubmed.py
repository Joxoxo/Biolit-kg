"""M1 数据采集：根据配置文件检索 PubMed，下载摘要并存入 SQLite。

第 2 步：读配置 → 拼检索式 → 检索
第 3 步：下载 → 解析 XML
第 4 步（当前）：分批下载全部文献并存入 SQLite，支持断点续跑

运行方法（在 biolit-kg 文件夹下）：
    python -m biolit.ingest.pubmed
"""
import datetime
import os
import time
import xml.etree.ElementTree as ET

import requests
import yaml
from dotenv import load_dotenv

from biolit.db import ROOT, get_connection

# PubMed 官方接口（E-utilities）的地址
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
BATCH_SIZE = 100   # 每次下载 100 篇（PubMed 建议单次不超过 200）
SLEEP = 0.4        # 没有 NCBI Key 时限速每秒 3 次请求，所以每次请求后等 0.4 秒

load_dotenv(ROOT / ".env")
EMAIL = os.getenv("NCBI_EMAIL", "")   # NCBI 要求标明联系邮箱，可选


# ---------- 读配置 ----------

def load_config(path=ROOT / "configs" / "pubmed.yaml") -> dict:
    """读取 YAML 配置文件，变成 Python 字典。"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------- 拼检索式 ----------

def build_query(cfg: dict) -> str:
    """拼出 PubMed 检索式：
    (药物1 OR 药物2 ...) AND (主题1 OR 主题2 ...) AND 过滤条件

    [tiab] 表示只在标题（title）和摘要（abstract）里找这个词
    """
    drugs = " OR ".join(f'"{d}"[tiab]' for d in cfg["drugs"])
    topics = " OR ".join(f'"{t}"[tiab]' for t in cfg["topics"])

    # 过滤条件：有摘要、英文、近 N 年发表（[dp] = 发表日期）
    start_year = datetime.date.today().year - cfg["years"]
    filters = f'hasabstract AND english[la] AND ("{start_year}"[dp] : "3000"[dp])'

    return f"({drugs}) AND ({topics}) AND {filters}"


# ---------- 检索 ----------

def esearch(query: str, max_results: int) -> tuple[int, list[int]]:
    """调用 esearch 接口。返回 (总共命中多少篇, 前 max_results 篇的 PMID 列表)。"""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,      # 最多返回多少个 PMID
        "retmode": "json",          # 返回 JSON 格式
        "sort": "relevance",        # 按相关性排序，最相关的排前面
        "tool": "biolit-kg",
        "email": EMAIL,
    }
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=30)
    r.raise_for_status()            # 请求失败（如网络错误、500）时直接报错
    result = r.json()["esearchresult"]
    return int(result["count"]), [int(x) for x in result["idlist"]]


# ---------- 下载 ----------

def efetch(pmids: list[int]) -> str:
    """下载一批文献的完整信息，返回 XML 文本。网络不稳定时最多重试 3 次。"""
    params = {
        "db": "pubmed",
        "id": ",".join(map(str, pmids)),   # 多个 PMID 用逗号连起来，一次请求下载
        "retmode": "xml",                  # efetch 只有 XML 格式才有完整摘要
        "tool": "biolit-kg",
        "email": EMAIL,
    }
    for attempt in range(1, 4):
        try:
            r = requests.get(f"{EUTILS}/efetch.fcgi", params=params, timeout=60)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            print(f"  第 {attempt} 次请求失败：{e}")
            time.sleep(2 * attempt)        # 失败后等一会儿再试，每次等得更久
    raise RuntimeError("连续 3 次请求失败，请检查网络后重试")


# ---------- 解析 XML ----------

def _text(elem) -> str:
    """取出一个 XML 元素里的全部文字。

    用 itertext() 而不是 .text，是因为标题里常有 <i>斜体</i> 等嵌套标签，
    .text 只能取到第一个标签之前的文字，会把标题截断。
    """
    return "".join(elem.itertext()).strip() if elem is not None else ""


def parse_articles(xml_text: str) -> list[dict]:
    """把 efetch 返回的 XML 解析成字典列表，每篇文献一个字典。"""
    root = ET.fromstring(xml_text)
    papers = []
    for art in root.findall(".//PubmedArticle"):
        citation = art.find("MedlineCitation")
        article = citation.find("Article")

        # 结构化摘要会分成好几段（BACKGROUND / METHODS / RESULTS ...），逐段拼起来
        parts = []
        for seg in article.findall("Abstract/AbstractText"):
            label = seg.get("Label")       # 段落标签，如 "RESULTS"；普通摘要没有
            parts.append(f"{label}: {_text(seg)}" if label else _text(seg))
        abstract = "\n".join(p for p in parts if p)
        if not abstract:
            continue                       # 没有摘要的跳过

        # 年份：大多数在 <Year> 里；少数只有 <MedlineDate>，如 "2021 Jan-Feb"，取前 4 位
        pub_date = article.find("Journal/JournalIssue/PubDate")
        year = _text(pub_date.find("Year")) or _text(pub_date.find("MedlineDate"))[:4]

        papers.append({
            "pmid": int(_text(citation.find("PMID"))),
            "title": _text(article.find("ArticleTitle")),
            "abstract": abstract,
            "year": int(year) if year.isdigit() else None,
            "journal": _text(article.find("Journal/Title")),
        })
    return papers


# ---------- 主流程：批量下载并入库 ----------

def main():
    cfg = load_config()
    query = build_query(cfg)
    print("检索式：\n", query, "\n")

    total, pmids = esearch(query, cfg["max_papers"])
    print(f"PubMed 共命中 {total} 篇，按相关性取前 {len(pmids)} 篇")
    time.sleep(SLEEP)

    conn = get_connection()

    # 断点续跑：先查出数据库里已有的 PMID，只下载还没有的
    done = {row["pmid"] for row in conn.execute("SELECT pmid FROM papers")}
    todo = [p for p in pmids if p not in done]
    print(f"数据库已有 {len(done)} 篇，本次需下载 {len(todo)} 篇\n")

    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start:start + BATCH_SIZE]
        papers = parse_articles(efetch(batch))

        # INSERT OR IGNORE：如果 pmid 已存在（主键冲突），自动跳过这一条
        # :pmid 这种写法叫"命名参数"，会自动从字典里取对应的值，比拼字符串更安全
        conn.executemany(
            "INSERT OR IGNORE INTO papers (pmid, title, abstract, year, journal) "
            "VALUES (:pmid, :title, :abstract, :year, :journal)",
            papers,
        )
        conn.commit()   # 每批提交一次：程序中途断了，已提交的批次也不会丢

        print(f"  第 {start // BATCH_SIZE + 1} 批：请求 {len(batch)} 篇，入库 {len(papers)} 篇")
        time.sleep(SLEEP)

    count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    print(f"\n完成！数据库共有 {count} 篇文献（data/biolit.db）")
    conn.close()


if __name__ == "__main__":
    main()
