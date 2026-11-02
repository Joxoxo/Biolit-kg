# BioLit-KG

基于大模型的生物医学文献知识图谱与智能问答平台。

> 🚧 开发中：数据采集、抽取、标准化、知识图谱、RAG 问答、评估已完成；网页演示与部署进行中

**主题**：口服抗栓药物（DOAC、华法林、氯吡格雷、替格瑞洛）的不良反应与药物相互作用

## 当前进展

| 模块 | 状态 | 说明 |
|---|---|---|
| M1 文献采集 | ✅ | PubMed 近 5 年 994 篇摘要，存入 SQLite |
| M2 大模型抽取 | ✅ | Gemini Flash-Lite + Pydantic 结构化输出；7 类关系、6 类实体、研究类型 |
| M3 标准化与校验 | ✅ | 同义词表、上下级关系；证据句逐字核验 + 数字核对 |
| M4 知识图谱 | ✅ | 约 640 个实体、1500 条关系；按"主体-关系-客体-对照药"聚合 |
| M5 RAG 问答 | ✅ | 向量检索 + 实体匹配 + 图谱查询的混合检索；带 PMID 引用，自动检查无效引用 |
| M6 评估 | ✅ | 60 篇人工标注（训练 40 + 盲评验证 20），见下方 |
| M7 网页与部署 | 🚧 | |

## 评估结果

v5 在 60 篇人工标注文献上：**Precision 98.8% / Recall 73.4% / F1 0.84**（宽松口径）。

根据训练集错误改进的提示词 v6，训练集 F1 从 0.79 升到 0.93，但在独立的盲评验证集上与 v5 持平（F1 0.77），判断为过拟合，正式版保留 v5。
详细的评估设计、错误分析和局限性见 [docs/评估报告.md](docs/评估报告.md)。

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
python -m biolit.graph.visualize                  # 生成图谱网页
python -m biolit.rag.index                        # 建立向量索引
python -m biolit.rag.answer "你的问题"             # 问答
```

## 目录结构

```
configs/      数据源与模型配置
data/         原始数据、处理结果、人工标注（不上传）
src/biolit/   核心代码：ingest / extract / normalize / graph / rag / eval / api
app/          Streamlit 网页
scripts/      一次性脚本
tests/        单元测试
docs/         评估报告等文档
```
