"""M7 FastAPI 后端：把抽取和问答能力封装成接口，供前端调用。

运行：
    uvicorn biolit.api.main:app --reload --port 8000

接口：
    GET  /health          健康检查
    POST /ask             RAG 问答
    POST /extract         在线抽取单篇摘要
    GET  /graph           知识图谱 JSON
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from biolit.extract.llm_client import DailyQuotaExceeded, GeminiClient
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
    title: str = Field(..., min_length=1, max_length=500)
    abstract: str = Field(..., min_length=1, max_length=15000)


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
def ask(req: AskRequest):
    try:
        ans = get_qa().ask(req.question, k=req.k)
    except DailyQuotaExceeded as e:
        raise HTTPException(status_code=429, detail=f"今日 API 额度已用完：{e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"问答失败：{e}")

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
def extract(req: ExtractRequest):
    try:
        client = get_client()
        resp = client.extract(req.title, req.abstract)
    except DailyQuotaExceeded as e:
        raise HTTPException(status_code=429, detail=f"今日 API 额度已用完：{e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抽取失败：{e}")

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



app.include_router(router)
