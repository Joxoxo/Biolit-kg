# BioLit-KG 前端

基于 React + Vite 的 BioLit-KG 交互式工作台，连接 FastAPI 后端。

## 运行

```bash
# 1. 先启动后端（项目根目录）
uvicorn biolit.api.main:app --reload --port 8000

# 2. 再启动前端（本目录）
npm install
npm run dev        # 开发预览（Vite，默认 http://localhost:3000）
npm run build      # 产出 dist/
```

要求 Node.js ≥ 20（Vite 7）。

## 技术栈

React 19 + TypeScript + Vite 7 + Tailwind CSS 3 + shadcn/ui + vis-network。

## 页面

1. **概览**（`src/pages/Home.tsx`）：工作台入口，展示各模块导航卡片与使用说明。
2. **关系索引**（`src/pages/RelationPage.tsx`）：药物对比查询与全部关系索引，数据源为 `src/data/relations.json`（60 篇人工标注结果的静态快照，2026-11 导出；标注更新后需要重新导出）。
3. **知识图谱**（`src/pages/GraphPage.tsx`）：调用 `/api/graph` 加载 `data/processed/graph.json`，使用 vis-network 渲染可拖拽、可缩放的交互图；支持按实体聚焦、按最小文献数过滤，点击边查看证据与 PMID。
4. **智能问答**（`src/pages/QaPage.tsx`）：调用 `/api/ask` 进行 RAG 问答，展示回答、知识图谱结论与引用文献。
5. **在线抽取**（`src/pages/ExtractPage.tsx`）：调用 `/api/extract` 对输入的标题与摘要执行大模型抽取，展示研究类型、实体与关系。

评估结果不在网页中展示，见 [`docs/评估报告.md`](../docs/评估报告.md)。

## 设计约定

- 黑白高对比 + 细线网格 + 安全橙 `#fe5000`；语义色：绿 `#047857`（优势/正确）、琥珀 `#b45309`（不一致/部分正确）、红 `#c2271a`（劣势/错误）。
- 等宽数字用 JetBrains Mono，中文用 Noto Sans SC（见 `index.html`、`src/index.css`）。
- 长效果文本悬停走马灯：`.marquee-track` 动画（遮罩为两端透明、中间不透明）。

## 已知边界

- 摘要级证据，非全文；证据强度有限，界面已注明仅供演示、不构成临床建议。
- RAG 与在线抽取依赖 Gemini API Key 与可用额度。
