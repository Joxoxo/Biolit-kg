---
title: BioLit-KG
emoji: 💊
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: LLM-built evidence base for oral antithrombotic drug safety
---

# BioLit-KG · 口服抗栓药安全证据库

从近 5 年约 1000 篇 PubMed 摘要中，用大模型自动抽取口服抗栓药（阿哌沙班、利伐沙班、达比加群、依度沙班、华法林、氯吡格雷、替格瑞洛）的不良反应和药物相互作用，构建知识图谱，支持带文献引用的问答，并与 FDA 药品说明书交叉验证。

源代码、评估报告：见 GitHub 仓库 Joxoxo/biolit-kg。

> 本站为方法学演示，结论仅反映文献摘要报告的结果，**不构成任何用药建议**。
> 为保护免费额度，问答每分钟限 5 次；当天额度用完后，只回答已缓存的问题（含页面上的示例问题）。
