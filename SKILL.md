---
name: external-learning
description: |
  外部学习工具。定期从外部信息源程序化采集技术情报，推送给主 Agent 深读。

  **当以下情况时使用此 Skill**:
  (1) 心跳触发时，轮询外部信息源
  (2) 主人问"最近有什么新东西"、"AI 有什么进展"
  (3) 需要了解某个领域的最新动态
  (4) 主人提到"学习"、"趋势"、"热门"、"前沿"

  **架构**: 程序化抓取 + 规则评分 + 主 Agent 深读落地。无 LLM 调用。
---

# External Learning

纯程序化采集，不调用 LLM。抓取 → 评分 → 推送 → 主人深读。

## 链路

```
gather.py（cron 每日 08:30）
  → 读 source_config.json
  → fetch RSS / DeepXiv / Web
  → 规则评分（源优先级 + 关键词 + 论文加分）
  → 写 candidates-*-YYYY-MM-DD.jsonl

evolution_orchestrator（cron 每日 08:35）
  → 读今日 JSONL
  → 筛选 ≥8 分候选
  → 推送给主人挑选 3-5 条 → 主 Agent 深读 → proposal_bridge → X-Memory
```

## 退役模块

以下模块不再参与主链路（保留文件便于回退）：

- `minimax_screener.py` — 原 MiniMax 元数据粗筛
- `minimax_reader.py` — 原 MiniMax 初读卡片生成
- `decider.py` — 原 GPT54 终判 keep/drop
- `llm_decider.py` — 原 LLM 调用桥
- `openclaw_model_executor.mjs` — 原 OpenClaw 模型执行器

## 测试

```bash
cd skills/external-learning
python3 -m pytest tests/ -v
```

14 tests OK.
