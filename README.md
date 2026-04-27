# External Learning：外部情报采集

## 是什么

`external-learning` 是 OpenClaw 的外部信息采集 Skill。**纯程序化**，不调用 LLM。

流程：抓取 → 规则评分 → 写 JSONL → orchestrator 心跳筛选 ≥8 分 → 推送给小一深读 → bridge → X-Memory。

深读和 judge 由主 Agent 直接做，不经过 MiniMax/GPT54 接力。

## 处理链路

```text
信息源(RSS/DeepXiv/Web)
      ↓
gather.py 程序化抓取 → 规则评分 → JSONL 候选清单
      ↓
evolution_orchestrator 心跳读取 → ≥8 分筛选
      ↓
推送给小一 → 小一深读前 3 条 → web_fetch 抓原文 → 写笔记进 X-Memory
      ↓
proposal_bridge → X-Memory → self-evolution
```

## 目录结构

```text
external-learning/
├── SKILL.md
├── README.md
├── modules/
│   ├── gather.py               # 唯一入口：程序化采集 + 规则评分
│   ├── gather_programmatic.py  # RSS / DeepXiv / GitHub Trending 抓取
│   ├── content_fetcher.py      # 全文抓取 + 缓存（深读时按需调用）
│   ├── deepread.py             # 深读笔记模板与保存
│   ├── quality.py              # 笔记质量检查与二次验证
│   ├── minimax_screener.py     # （退役）LLM 粗筛
│   ├── minimax_reader.py       # （退役）LLM 初读
│   ├── decider.py              # （退役）LLM 终判
│   ├── llm_decider.py          # （退役）LLM 调用桥
│   ├── openclaw_model_executor.mjs  # （退役）模型执行器
│   └── sources/
│       ├── __init__.py
│       └── source_config.json  # 信息源配置
└── tests/
    └── test_external_learning.py
```

## 快速开始

```bash
cd external-learning/modules
python3 gather.py           # 增量采集
python3 gather.py --force   # 全量采集
```

采集完成后，`evolution_orchestrator` 心跳会自动读取 JSONL，筛选 ≥8 分候选推送。主 Agent 收到候选列表后挑选最有价值的深读。

## 信息源

| 源 | 类型 | 主题 |
|------|------|------|
| arXiv via DeepXiv | deepxiv | AI agent、LLM memory、autonomous agent |
| Google DeepMind | rss | 官方研究博客 |
| Meta AI Research | rss | 官方研究博客 |
| Hacker News | rss | 技术社区 |
| GitHub Trending | fetch | AI 相关开源项目 |
| IEEE Spectrum | rss | 工程与科技 |
| Nature News | rss | 科学前沿 |
| Bloomberg Technology | rss | 科技商业 |
| Ars Technica | rss | 深度科技报道 |
| Hugging Face Blog | rss | 模型与开源生态 |

配置在 `modules/sources/source_config.json`，支持 `rss` / `deepxiv` / `fetch` 三种类型。

## 评分规则

纯规则，无 LLM：

- 源优先级加分（P1 +1.2，P2 +1.0，P3 +0.8）
- 论文源 +2.2
- 关键词命中 +0.5/个
- 基础分 3.5

最终 score ≥ 8.0 的候选进入深读推荐。

## 测试

```bash
cd external-learning
python3 -m pytest tests/ -v
```

14 个测试全绿。

## 2026-04-27 更新

- **简化链路**：砍掉 MiniMax 粗筛、MiniMax 初读、GPT54 终判三个 LLM 调用
- 深读和 judge 由主 Agent 直接做（省 token、省时间、判断力更强）
- orchestrator 心跳自动推送 ≥8 分候选给主人挑选
- `minimax_screener` / `minimax_reader` / `decider` / `llm_decider` 标记为退役
- `WORKSPACE_ROOT` 统一走 runtime_config
