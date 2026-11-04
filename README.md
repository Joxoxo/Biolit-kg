# BioLit-KG

基于大模型的生物医学文献知识图谱与智能问答平台。

> 基于 React + FastAPI 的交互式演示：关系索引、知识图谱可视化、RAG 智能问答、在线抽取。

**主题**：口服抗栓药物（DOAC、华法林、氯吡格雷、替格瑞洛）的不良反应与药物相互作用

## 当前进展

| 模块 | 状态 | 说明 |
|---|---|---|
| M1 文献采集 | ✅ | PubMed 近 5 年 994 篇摘要，存入 SQLite |
| M2 大模型抽取 | ✅ | Gemini Flash-Lite + Pydantic 结构化输出；7 类关系、6 类实体、研究类型 |
| M3 标准化与校验 | ✅ | 同义词表、上下级关系；证据句逐字核验 + 数字核对 |
| M4 知识图谱 | ✅ | 648 个实体、1538 条关系；按"主体-关系-客体-对照药"聚合 |
| M5 RAG 问答 | ✅ | 向量检索 + 实体匹配 + 图谱查询的混合检索；带 PMID 引用，自动检查无效引用 |
| M6 评估 | ✅ | 抽取：60 篇人工标注（训练 40 + 盲评验证 20）；问答：30 题评测集，三系统消融对比 |
| M7 网页与部署 | ✅ | React + Vite 前端 + FastAPI 后端，本地联调通过 |

## 评估结果

v5 在 60 篇人工标注文献上：**Precision 98.8% / Recall 73.4% / F1 0.84**（宽松口径）。

根据训练集错误改进的提示词 v6，训练集 F1 从 0.79 升到 0.93，但在独立的盲评验证集上与 v5 持平（F1 0.77），判断为过拟合，正式版保留 v5。
详细的评估设计、错误分析和局限性见 [docs/评估报告.md](docs/评估报告.md)。

**问答评估**（30 题，其中 6 题为文献库中查不到答案的范围外题）：

| 系统 | 检索 P@5 | 要点覆盖率 | 范围外题拒答率 |
|---|---|---|---|
| 纯大模型 | — | 59.9% | 0% |
| 向量 RAG | 83.3% | 76.9% | 100% |
| GraphRAG（向量 + 实体 + 图谱） | 85.8% | 76.2% | 83.3% |

检索增强明显减少了编造；加入知识图谱没有进一步提升问答效果。自动阅卷经人工复核，κ = 0.85。
详见 [docs/问答评估报告.md](docs/问答评估报告.md)。

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # 然后在 .env 里填入 API Key
pip install -e .
python scripts/hello_llm.py                       # 测试 API 连通

# 完整流程
python -m biolit.ingest.pubmed                    # 采集文献
python -m biolit.extract.run                      # 大模型抽取
python -m biolit.normalize.run                    # 标准化 + 证据核验
python -m biolit.graph.build                      # 构建知识图谱
python -m biolit.rag.index                        # 建立向量索引

# 启动网页演示（需两个终端）
uvicorn biolit.api.main:app --reload --port 8000  # 后端 API
cd app && npm install && npm run dev              # 前端
```

## 目录结构

```
configs/      数据源与模型配置
data/         原始数据、处理结果、人工标注（不上传）
src/biolit/   核心代码：ingest / extract / normalize / graph / rag / eval / api
app/          React + Vite 网页
scripts/      一次性脚本
tests/        单元测试
docs/         评估报告等文档
```
