"""M6 问答评估 · 第 3 步：用大模型当"阅卷老师"，对照你写的参考要点给三个系统的回答打分。

为什么用大模型打分：30 题 × 3 个系统 = 90 份回答，人工逐条打分太慢。
但大模型打分不一定可靠，所以之后会抽一部分让你人工复核，计算你和模型的一致率。

减少打分偏差的做法：
1. 盲评：三份回答打乱顺序，只标"回答 1/2/3"，阅卷模型不知道哪份来自哪个系统
2. 同一题的三份回答一起打分（一次调用），尺度一致，也省额度
3. 只看参考要点和被引用文献的摘要，不让模型自由发挥"它觉得对不对"
已知局限：阅卷模型和回答模型是同一个（gemini-3.5-flash-lite），可能偏好自己的写法，人工复核时要留意。

额度：每题 1 次，共 30 次。

运行（在 biolit-kg 文件夹下，需先跑完 qa_run）：
    python -m biolit.eval.qa_judge
输出：data/annotations/qa_judge.json
"""
import json
import random
import time
from enum import Enum

import yaml
from openpyxl import load_workbook
from pydantic import BaseModel, Field

from biolit.db import ROOT, get_connection
from biolit.extract.llm_client import DailyQuotaExceeded, GeminiClient
from biolit.rag.answer import MODES

QUESTIONS = ROOT / "configs" / "qa_questions.yaml"
GOLD = ROOT / "data" / "annotations" / "qa_gold_已审核.xlsx"
RUNS = ROOT / "data" / "annotations" / "qa_runs.json"
OUT = ROOT / "data" / "annotations" / "qa_judge.json"
MIN_INTERVAL = 4.5


# ---------- 打分结果的格式 ----------

class Coverage(str, Enum):
    full = "覆盖"
    partial = "部分覆盖"
    none = "未覆盖"


class Support(str, Enum):
    full = "支持"
    partial = "部分支持"
    none = "不支持"


class PointVerdict(BaseModel):
    point: int = Field(description="参考要点编号，从 1 开始")
    verdict: Coverage


class CitationVerdict(BaseModel):
    pmid: int
    verdict: Support = Field(description="回答中引用该 PMID 的那句结论，是否被这篇摘要支持")


class AnswerJudgement(BaseModel):
    answer: int = Field(description="回答编号")
    points: list[PointVerdict]
    citations: list[CitationVerdict]
    contradictions: int = Field(description="回答中与参考要点相矛盾的结论条数")


class Judgement(BaseModel):
    answers: list[AnswerJudgement]


class RefusalVerdict(BaseModel):
    answer: int
    refused: bool = Field(description="是否明确说明检索到的文献未涉及、无法根据现有材料回答")
    substantive: bool = Field(description="是否仍然给出了实质性的医学结论（如'会增加出血风险'）")


class RefusalJudgement(BaseModel):
    answers: list[RefusalVerdict]


JUDGE_PROMPT = """你是一名严格的临床药学阅卷老师。你会收到：一道问题、参考要点（标准答案）、若干份匿名回答，以及回答中引用到的文献摘要。

请对每份回答分别判断：
1. 参考要点覆盖：逐条判断回答是否表达了该要点的核心意思。
   - 覆盖：核心结论和方向都对（具体数字可以不同或缺失）
   - 部分覆盖：只提到一部分，或方向对但关键限定条件缺失（例如漏了人群、对照药）
   - 未覆盖：没提到，或说法与要点相反
2. 引用核查：对回答中出现的每个 [PMID:xxx]，判断引用它的那句结论是否被对应摘要支持。
   - 支持 / 部分支持（摘要有相关内容但结论被夸大或张冠李戴）/ 不支持
   - 回答没有引用任何 PMID 时，citations 返回空列表
3. 矛盾：统计回答中与参考要点明确相反的结论条数。

只依据参考要点和给出的摘要判断，不要用你自己的医学知识去评判对错。"""

REFUSAL_PROMPT = """你是一名阅卷老师。下面这道问题在系统的文献库中没有任何相关文献，理想的回答应当明确说明"检索到的文献未涉及"，
而不是凭空给出医学结论。请对每份匿名回答判断：
- refused：是否明确说明文献未涉及 / 无法根据现有材料回答
- substantive：是否仍然给出了实质性的医学结论（比如"会增加出血风险""机制是诱导 CYP3A4"）
两者可以同时为真（先说文献未涉及，又补充了结论）。"""


def load_points() -> dict[str, list[str]]:
    ws = load_workbook(GOLD, read_only=True)["题目"]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] and row[7]:
            out[row[0]] = [line.strip() for line in str(row[7]).splitlines() if line.strip()]
    return out


def main():
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
    runs = json.loads(RUNS.read_text(encoding="utf-8"))
    points = load_points()
    judged = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    conn = get_connection()
    llm = GeminiClient()

    try:
        for q in questions:
            qid = q["id"]
            if qid in judged:
                continue
            answers = {m: runs.get(f"{qid}|{m}") for m in MODES}
            if not all(answers.values()):
                print(f"{qid}：三个系统还没全部回答，跳过")
                continue

            # 盲评：按题号固定随机种子打乱顺序，重跑时顺序不变
            order = list(MODES)
            random.Random(qid).shuffle(order)
            blind = "\n\n".join(f"### 回答 {i}\n{answers[m]['answer']}" for i, m in enumerate(order, 1))

            before = llm.calls
            if q["scope"] == "out":
                result = llm.generate(f"## 问题\n{q['question']}\n\n## 待评回答\n{blind}",
                                      REFUSAL_PROMPT, schema=RefusalJudgement)
            else:
                pts = "\n".join(f"{i}. {p}" for i, p in enumerate(points[qid], 1))
                cited = sorted({pm for m in order for pm in answers[m]["cited"]})
                abstracts = "\n\n".join(
                    f"[PMID:{r['pmid']}] {r['title']}\n{r['abstract']}" for r in conn.execute(
                        f"SELECT pmid, title, abstract FROM papers WHERE pmid IN ({','.join('?' * len(cited))})",
                        cited)) if cited else "（三份回答都没有引用文献）"
                result = llm.generate(
                    f"## 问题\n{q['question']}\n\n## 参考要点\n{pts}\n\n## 待评回答\n{blind}\n\n## 被引用文献的摘要\n{abstracts}",
                    JUDGE_PROMPT, schema=Judgement)

            # 把"回答编号"还原成系统名称
            judged[qid] = {"scope": q["scope"], "n_points": len(points.get(qid, [])),
                           "results": {order[a.answer - 1]: a.model_dump(mode="json") for a in result.answers
                                       if 1 <= a.answer <= len(order)}}
            OUT.write_text(json.dumps(judged, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{qid} 已打分")
            if llm.calls > before:
                time.sleep(MIN_INTERVAL)
    except DailyQuotaExceeded:
        print("\n今日额度已用完，已保存进度，明天重新运行即可续跑。")

    print(f"\n已打分 {len(judged)} 题；模型调用 {llm.calls} 次，缓存命中 {llm.cache_hits} 次")


if __name__ == "__main__":
    main()
