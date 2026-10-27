# BioLit-KG

基于大模型的生物医学文献知识图谱与智能问答平台。

> 🚧 开发中

## 功能（规划）

- 从 PubMed 自动采集文献摘要
- 用大模型抽取实体与关系，并做幻觉检测
- 构建可交互的知识图谱
- RAG 问答：回答附文献引用
- 多模型抽取效果评估
- 网页演示 + Docker 部署

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # 然后在 .env 里填入 API Key
python scripts/hello_llm.py
```

## 目录结构

```
configs/      数据源与模型配置
data/         原始数据、处理结果、人工标注（不上传）
src/biolit/   核心代码：ingest / extract / normalize / graph / rag / eval / api
app/          Streamlit 网页
scripts/      一次性脚本
tests/        单元测试
```
