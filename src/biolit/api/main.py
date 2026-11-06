"""M7 FastAPI 后端：把抽取和问答能力封装成接口，供前端调用。

运行：
    uvicorn biolit.api.main:app --reload --port 8000

部署时（Docker / Hugging Face Spaces），同一个服务还会托管打包好的网页（app/dist），只需要一个端口。

公开演示的额度保护（环境变量可调）：
- DEMO_RATE_PER_MIN：每个访客每分钟最多几次问答 / 抽取（默认 5）
- DEMO_DAILY_CALLS ：全站每天最多真正调用几次模型（默认 300，免费额度每天约 500）
  超过后进入"只读缓存"模式：已经问过的问题（包括页面上的示例问题）照常回答，新问题提示明天再试
- 在线抽取另有更严的限制（输入长、最容易被滥用）：
  DEMO_EXTRACT_PER_IP 每人每天几次（默认 3），DEMO_EXTRACT_DAILY 全站每天几次（默认 20）
  只计真正调用模型的次数：重复提交同一篇摘要、使用示例摘要都读缓存，不计次

接口：
    GET  /health          健康检查
    POST /ask             RAG 问答
    POST /extract         在线抽取单篇摘要
    GET  /graph           知识图谱 JSON
    GET  /drugs           药物安全档案可选的药物
    GET  /profile/{drug}  某个药的安全档案（比较结论 + 相互作用与代谢 + 说明书比对）
    GET  /evidence        展开某一行时，取对应文献的标题和证据句
"""
import json
import os
import threading
import time
from collections import Counter, defaultdict, deque
from datetime import date
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from biolit.db import ACTIVE_VERSION, ROOT, get_connection
from biolit.api.profile import DRUGS, build_profile
from biolit.extract.llm_client import CACHE_ONLY, CacheMiss, DailyQuotaExceeded, GeminiClient
from biolit.extract.schema import ExtractionResult
from biolit.graph.build import GRAPH_PATH
from biolit.rag.answer import QA

app = FastAPI(title="BioLit-KG API", version="0.1.0")
router = APIRouter(prefix="/api")

# 允许前端开发服务器跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- lazy singletons ----------

_qa: QA | None = None
_client: GeminiClient | None = None


def get_qa() -> QA:
    global _qa
    if _qa is None:
        _qa = QA()
    return _qa


def get_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client


# ---------- 额度保护 ----------

RATE_PER_MIN = int(os.getenv("DEMO_RATE_PER_MIN", "5"))
DAILY_CALLS = int(os.getenv("DEMO_DAILY_CALLS", "300"))
_lock = threading.Lock()
_recent: dict[str, deque] = defaultdict(deque)       # 每个访客最近一分钟的请求时间
_usage = {"date": date.today(), "calls": 0}          # 今天全站真正调用模型的次数


def client_ip(request: Request) -> str:
    # 部署在 Hugging Face 时前面有一层代理，真实 IP 在 X-Forwarded-For 的第一个
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def check_rate(ip: str):
    now = time.time()
    with _lock:
        q = _recent[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_PER_MIN:
            raise HTTPException(status_code=429, detail=f"请求太频繁：每分钟最多 {RATE_PER_MIN} 次，请稍后再试")
        q.append(now)


def budget_left() -> bool:
    with _lock:
        if _usage["date"] != date.today():
            _usage.update(date=date.today(), calls=0)
        return _usage["calls"] < DAILY_CALLS


def spend(n: int):
    with _lock:
        _usage["calls"] += n


EXTRACT_PER_IP = int(os.getenv("DEMO_EXTRACT_PER_IP", "3"))
EXTRACT_DAILY = int(os.getenv("DEMO_EXTRACT_DAILY", "20"))
_extract_usage = {"date": date.today(), "total": 0, "by_ip": Counter()}
EXAMPLE_PMID = 37839687        # "填入示例摘要"用的文献，部署前用 scripts/warm_cache.py 预先抽好


def extract_allowed(ip: str) -> bool:
    with _lock:
        if _extract_usage["date"] != date.today():
            _extract_usage.update(date=date.today(), total=0, by_ip=Counter())
        return (_extract_usage["total"] < EXTRACT_DAILY and _extract_usage["by_ip"][ip] < EXTRACT_PER_IP
                and _usage["calls"] < DAILY_CALLS)


def spend_extract(ip: str, n: int):
    with _lock:
        _extract_usage["total"] += n
        _extract_usage["by_ip"][ip] += n
        _usage["calls"] += n


# ---------- request / response models ----------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=10)


class AskResponse(BaseModel):
    question: str
    answer: str
    cited: list[int]
    invalid_citations: list[int]
    papers: list[dict]
    graph_facts: list[dict]


class ExtractRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    abstract: str = Field(..., min_length=1, max_length=6500)   # 摘要平均约 1800 字符、最长约 6000；防止贴入全文


class ExtractResponse(BaseModel):
    study_type: str
    entities: list[dict]
    relations: list[dict]
    model: str
    input_tokens: int
    output_tokens: int
    seconds: float



# ---------- endpoints ----------

@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request):
    check_rate(client_ip(request))
    qa = get_qa()
    CACHE_ONLY.set(not budget_left())       # 今天的演示额度用完了：只回答已缓存的问题
    before = qa.llm.calls
    try:
        ans = qa.ask(req.question, k=req.k)
    except CacheMiss:
        raise HTTPException(status_code=429, detail="今天的演示额度已用完，可以试试页面上的示例问题，或明天再来")
    except DailyQuotaExceeded as e:
        raise HTTPException(status_code=429, detail=f"今日 API 额度已用完：{e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"问答失败：{e}")
    finally:
        spend(qa.llm.calls - before)

    return AskResponse(
        question=ans.question,
        answer=ans.text,
        cited=ans.cited,
        invalid_citations=ans.invalid_citations,
        papers=[
            {
                "pmid": p.pmid,
                "title": p.title,
                "year": p.year,
                "journal": p.journal,
                "study_type": p.study_type,
                "score": round(p.score, 4),
                "matched": p.matched,
            }
            for p in ans.retrieval.papers
        ],
        graph_facts=ans.retrieval.graph_facts,
    )


@router.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest, request: Request):
    ip = client_ip(request)
    check_rate(ip)
    client = get_client()
    CACHE_ONLY.set(not extract_allowed(ip))      # 次数用完：只返回已经抽取过的摘要（如示例摘要）
    before = client.calls
    try:
        resp = client.extract(req.title, req.abstract)
    except CacheMiss:
        raise HTTPException(status_code=429, detail=f"在线抽取每人每天限 {EXTRACT_PER_IP} 次，今天的次数已用完。"
                                                    f"可以点\"填入示例摘要\"体验，或明天再来")
    except DailyQuotaExceeded as e:
        raise HTTPException(status_code=429, detail=f"今日 API 额度已用完：{e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抽取失败：{e}")
    finally:
        spend_extract(ip, client.calls - before)

    result: ExtractionResult = resp.result
    return ExtractResponse(
        study_type=result.study_type,
        entities=[e.model_dump() for e in result.entities],
        relations=[r.model_dump() for r in result.relations],
        model=resp.model,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        seconds=resp.seconds,
    )


@router.get("/graph")
def graph():
    if not GRAPH_PATH.exists():
        raise HTTPException(status_code=503, detail="图谱文件不存在，请先运行 python -m biolit.graph.build")
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))



@router.get("/extract/example")
def extract_example():
    """示例摘要：上线前已预先抽取并存进缓存，访客点了秒出结果、不计次数。"""
    row = get_connection().execute("SELECT pmid, title, abstract FROM papers WHERE pmid = ?", (EXAMPLE_PMID,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="示例文献不存在")
    return {"pmid": row["pmid"], "title": row["title"], "abstract": row["abstract"],
            "limit_per_day": EXTRACT_PER_IP}


@router.get("/drugs")
def drugs():
    return [{"id": k, "zh": v} for k, v in DRUGS.items()]


@router.get("/profile/{drug}")
def profile(drug: str):
    if drug not in DRUGS:
        raise HTTPException(status_code=404, detail=f"不支持的药物：{drug}")
    if not GRAPH_PATH.exists():
        raise HTTPException(status_code=503, detail="图谱文件不存在，请先运行 python -m biolit.graph.build")
    return build_profile(drug)


@router.get("/evidence")
def evidence(pmids: str, a: str, b: str = ""):
    """pmids：逗号分隔（最多 20 篇）；a、b：关系两端的实体（标准化名称），只返回同时涉及 a 和 b 的证据句。"""
    ids = [int(x) for x in pmids.split(",") if x.strip().isdigit()][:20]
    if not ids:
        return []
    conn = get_connection()
    marks = ",".join("?" * len(ids))
    papers = {r["pmid"]: dict(r) for r in conn.execute(
        f"SELECT p.pmid, p.title, p.year, p.journal, e.study_type FROM papers p "
        f"LEFT JOIN extractions e ON e.pmid = p.pmid AND e.prompt_version = ? AND e.status = 'ok' "
        f"WHERE p.pmid IN ({marks})", (ACTIVE_VERSION, *ids))}
    for pm in papers:
        papers[pm]["sentences"] = []
    for r in conn.execute(
            f"SELECT pmid, subject_norm, object_norm, comparator_norm, evidence FROM relations "
            f"WHERE prompt_version = ? AND pmid IN ({marks})", (ACTIVE_VERSION, *ids)):
        names = {r["subject_norm"], r["object_norm"], r["comparator_norm"]}
        if a in names and (not b or b in names) and r["evidence"] not in papers[r["pmid"]]["sentences"]:
            papers[r["pmid"]]["sentences"].append(r["evidence"])
    return sorted(papers.values(), key=lambda p: -(p["year"] or 0))


app.include_router(router)

# 部署时：同一个服务托管打包好的网页。必须放在 include_router 之后，否则会盖住 /api 接口
WEB_DIST = ROOT / "app" / "dist"
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
