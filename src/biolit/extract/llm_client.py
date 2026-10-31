"""M2 模型调用：把"调用大模型"封装成统一接口。

为什么要封装：
抽取代码只调用 client.extract(...)，不关心背后是 Gemini 还是 DeepSeek。
以后换模型只需要改 .env，不用改抽取代码（第 8 天做模型对比时就靠这个）。

自测方法（在 biolit-kg 文件夹下）：
    python -m biolit.extract.llm_client
"""
import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from biolit.db import ROOT
from biolit.extract.prompts import SYSTEM_PROMPT, build_user_prompt
from biolit.extract.schema import ExtractionResult

load_dotenv(ROOT / ".env")

# 这些错误是"临时性"的，等一会儿再试通常就好：
# 429 = 请求太频繁（超过每分钟限额）；500/503 = 服务器出错或太忙
RETRYABLE = {429, 500, 503}
MAX_RETRIES = 5


class DailyQuotaExceeded(Exception):
    """每日免费额度已用完：重试没有意义，需要等第二天。"""


@dataclass
class LLMResponse:
    """一次调用的结果：抽取内容 + 用量信息（用于统计成本和速度）。"""
    result: ExtractionResult
    model: str
    input_tokens: int
    output_tokens: int
    seconds: float


class GeminiClient:
    def __init__(self, model: str | None = None):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("没有找到 GEMINI_API_KEY，请检查 .env 文件")
        self.client = genai.Client(api_key=api_key)
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    def _retry(self, fn):
        """执行一次模型调用；遇到临时错误自动重试，等待时间逐次翻倍（5、10、20、40 秒）。"""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return fn()
            except errors.APIError as e:
                # 429 有两种：每分钟超限（等一会儿就好）和每日超限（今天不会好了）
                # 每日超限的错误信息里会带 "PerDay"
                if e.code == 429 and "PerDay" in str(e):
                    raise DailyQuotaExceeded(str(e)) from e
                if e.code not in RETRYABLE or attempt == MAX_RETRIES:
                    raise                     # 不可重试的错误（如 Key 无效），或已试满 5 次
                wait = 5 * 2 ** (attempt - 1)
                print(f"  [{e.code}] 服务器暂时不可用，{wait} 秒后第 {attempt + 1} 次尝试…")
                time.sleep(wait)

    def extract(self, title: str, abstract: str) -> LLMResponse:
        """从一篇摘要中抽取实体和关系。"""
        return self._retry(lambda: self._call(title, abstract))

    def generate(self, contents: str, system: str, schema=None):
        """通用调用：给定系统提示词和内容，返回文本；若给了 schema（Pydantic 类），返回校验后的对象。
        RAG 的"理解问题"和"生成回答"都用这个方法。"""
        def call():
            config = types.GenerateContentConfig(system_instruction=system)
            if schema is not None:
                config.response_mime_type = "application/json"
                config.response_schema = schema
            response = self.client.models.generate_content(model=self.model, contents=contents, config=config)
            if schema is None:
                return response.text
            return response.parsed or schema.model_validate_json(response.text)
        return self._retry(call)

    def _call(self, title: str, abstract: str) -> LLMResponse:
        """真正发出一次请求（不含重试）。"""
        start = time.time()
        response = self.client.models.generate_content(
            model=self.model,
            contents=build_user_prompt(title, abstract),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,        # 系统提示词：角色和规则
                response_mime_type="application/json",   # 要求只返回 JSON
                response_schema=ExtractionResult,        # 要求 JSON 严格符合我们定义的格式
            ),
        )
        # response.parsed：SDK 已经按 ExtractionResult 校验并转换好的对象
        result = response.parsed
        if result is None:   # 极少数情况下模型返回的 JSON 不合规，这里手动再校验一次
            result = ExtractionResult.model_validate_json(response.text)

        usage = response.usage_metadata
        return LLMResponse(
            result=result,
            model=self.model,
            input_tokens=usage.prompt_token_count or 0,
            output_tokens=usage.candidates_token_count or 0,
            seconds=round(time.time() - start, 1),
        )


if __name__ == "__main__":
    # 自测：从数据库取 1 篇文献，抽取后打印结果
    from biolit.db import get_connection

    paper = get_connection().execute(
        "SELECT pmid, title, abstract FROM papers WHERE pmid = 37839687"
    ).fetchone()
    print(f"PMID {paper['pmid']}：{paper['title']}\n")

    resp = GeminiClient().extract(paper["title"], paper["abstract"])
    print(f"模型 {resp.model} | 用时 {resp.seconds} 秒 | "
          f"输入 {resp.input_tokens} tokens，输出 {resp.output_tokens} tokens\n")

    print("【实体】")
    for e in resp.result.entities:
        print(f"  {e.type:<14} {e.name}")
    print("\n【关系】")
    for r in resp.result.relations:
        extra = []
        if r.effect:
            extra.append(f"效果：{r.effect}")
        if r.comparator:
            extra.append(f"对照：{r.comparator}")
        if r.population:
            extra.append(f"人群：{r.population}")
        print(f"  {r.subject} --{r.relation}--> {r.object}  {' | '.join(extra)}")
        print(f"    证据：{r.evidence}")
