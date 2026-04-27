---
name: external-learning
description: |
  外部学习工具 v3。定期从外部信息源采集技术情报，MiniMax 初读，GPT54 终判，主 Agent 深读落地。

  **当以下情况时使用此 Skill**:
  (1) 心跳触发时，轮询外部信息源
  (2) 主人问"最近有什么新东西"、"AI 有什么进展"
  (3) 需要了解某个领域的最新动态
  (4) 主人提到"学习"、"趋势"、"热门"、"前沿"

  **架构**: 程序化抓取 + MiniMax 初读 + GPT54 终判 + 深读落地。
---

# External Learning v3

从外部世界主动学习，产出可操作的知识，而不是标题摘要。

## 当前架构

```text
external-learning/
├── SKILL.md
├── README.md
├── modules/
│   ├── __init__.py
│   ├── gather.py              # 唯一采集入口
│   ├── gather_programmatic.py # RSS / DeepXiv / GitHub Trending 抓取实现
│   ├── minimax_reader.py      # MiniMax 初读层
│   ├── decider.py             # GPT54 终判层
│   ├── deepread.py            # 深读笔记生成与保存
│   ├── quality.py             # 笔记质量与二次验证
│   └── sources/
│       ├── __init__.py
│       └── source_config.json
└── tests/
    └── test_external_learning.py
```

## 职责边界

- `gather.py` 是采集入口。
- `gather_programmatic.py` 实现 RSS、DeepXiv、GitHub Trending 三类抓取。
- `minimax_reader.py` 生成初读卡片。
- `decider.py` 使用 GPT54 产生最终 keep/drop 判断。
- `deepread.py` 生成并保存深读笔记。
- `quality.py` 做笔记质量评分和二次验证检查。
- `source_config.json` 是信息源配置入口。

## 流程

1. `gather(force_all=False)` 读取 `source_config.json`，按心跳时间判断要更新的源。
2. 程序化抓取 RSS、DeepXiv、GitHub Trending，写入 `memory/learning/candidates-{source}-{date}.md`。
3. `filter_for_deep_read()` 调用 `MiniMax` 生成 reading cards。
4. `GPT54` 对 reading cards 做最终判断，只输出达到阈值的条目。
5. `deep_read_batch()` 生成深读笔记模板。
6. 主 Agent 读取原文、做交叉验证、填写笔记。
7. `save_notes()` 过滤低质量笔记并保存到 `memory/learning/{date}.md`。

## 模型执行

模型执行由 `modules/openclaw_model_executor.mjs` 接入 OpenClaw 已配置的模型注册表和鉴权存储。
Skill 只传入 prompt 和模型别名，不读取 API key、不维护 provider URL。

固定模型别名：

- 初读：`Minimax`
- 终判：`GPT54`


## 使用

```python
from modules.gather import gather, merge_all_candidates
from modules.deepread import filter_for_deep_read, deep_read_batch, save_notes

results = gather(force_all=False)
candidates = merge_all_candidates()
selected = filter_for_deep_read(candidates, min_score=8.0, max_count=5)
notes = deep_read_batch(selected)
save_notes(notes)
```

## 信息源

信息源只在 `modules/sources/source_config.json` 中定义。当前代码支持：

- `rss`: RSS feed
- `deepxiv`: DeepXiv arXiv 搜索
- `fetch`: GitHub Trending 页面抓取

新增源必须接入这三类之一，或先扩展 `gather_programmatic.py` 的抓取实现。

## 候选格式

候选文件写入 `memory/learning/candidates-{source}-{date}.md`：

```markdown
# {源名称} 候选清单 {date}

| # | 标题 | URL | 分数 | 理由 | 发布时间 |
|---|------|-----|------|------|----------|
| 1 | xxx | https://example.com | 8.5 | 论文源; 摘要信息充足 | 2026-04-19 |
```

## 深读笔记要求

每条笔记必须包含：

- `来源等级`: 摘要级 / 原文级 / 多源验证级
- `二次验证`: 交叉来源、反证检查或实现核对
- `核心内容`: 3-5 句具体方法、数据、结果
- `对我们的启发`: 可执行，不写空话
- `落地评估`: 相关模块、改动规模、前置条件、优先级

质量分低于 6 的笔记不会入库。

## 心跳集成

```bash
cd /root/.openclaw/skills/external-learning/modules
python3 - <<'PY'
from gather import gather
results = gather()
print(f"Gathered {sum(len(v) for v in results.values())} candidates")
PY
```

## 通知规则

主动通知：

- GPT54 终判分数 >= 9
- 与主人业务或当前系统进化直接相关的 P0 条目
- 外部学习超过 48 小时未执行

其他常规结果静默记录。
