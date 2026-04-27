# External Learning：外部情报采集与深度学习

## 是什么

`external-learning` 是 OpenClaw 的外部信息采集 Skill，定期从多源采集 AI/科技前沿情报，经粗筛→初读→终判→深读→沉淀后，通过 `proposal_bridge` 桥接到 `self-evolution` 进化系统。

## 处理链路

```text
信息源(RSS/DeepXiv/Web)
      ↓
gather.py 程序化抓取 → JSONL 候选清单
      ↓
minimax_screener.py 元数据粗筛
      ↓
minimax_reader.py MiniMax 初读 → reading cards
      ↓
decider.py GPT54 终判 keep/drop
      ↓
deepread.py 深读笔记 + quality.py 质量验证
      ↓
proposal_bridge → X-Memory → self-evolution
```

## 目录结构

```text
external-learning/
├── SKILL.md                    # OpenClaw Skill 声明
├── README.md
├── modules/
│   ├── gather.py               # 采集入口
│   ├── gather_programmatic.py  # RSS / DeepXiv / GitHub Trending 抓取
│   ├── content_fetcher.py      # 全文内容抓取 + 缓存
│   ├── minimax_screener.py     # MiniMax 元数据粗筛
│   ├── minimax_reader.py       # MiniMax 初读卡片生成
│   ├── decider.py              # GPT54 最终 keep/drop 判断
│   ├── llm_decider.py          # 模型调用桥（通过 OpenClaw 运行时）
│   ├── deepread.py             # 深读笔记模板与保存
│   ├── quality.py              # 笔记质量检查与二次验证
│   ├── openclaw_model_executor.mjs  # OpenClaw 模型执行器
│   └── sources/
│       ├── __init__.py
│       └── source_config.json  # 信息源配置
└── tests/
    └── test_external_learning.py
```

## 快速开始

### 命令行

```bash
cd external-learning/modules
python3 gather.py           # 增量采集
python3 gather.py --force   # 全量采集（忽略间隔限制）
```

### Python API

```python
from modules.gather import gather, merge_all_candidates
from modules.deepread import filter_for_deep_read, deep_read_batch, save_notes

results = gather(force_all=False)
candidates = merge_all_candidates()
selected = filter_for_deep_read(candidates, min_score=8.0, max_count=5)
notes = deep_read_batch(selected)
save_notes(notes)
```

### 集成到 self-evolution

```bash
# orchestrator 心跳自动读取 JSONL 并桥接
cd self-evolution
PYTHONPATH=".:modules:../X-Memory" python3 modules/evolution_orchestrator.py heartbeat
```

≥8 分的深读候选会自动写入 X-Memory 并触发 proposal 创建。

## 当前信息源

| 源 | 类型 | 说明 |
|------|------|------|
| arXiv via DeepXiv | deepxiv | AI agent / LLM memory / autonomous agent 等主题 |
| Google DeepMind | rss | 官方博客 |
| Meta AI Research | rss | 官方博客 |
| Hacker News | rss | 技术社区 |
| GitHub Trending | fetch | AI 相关项目 |
| IEEE Spectrum | rss | 工程与科技 |
| Nature News | rss | 科学前沿 |
| Bloomberg Technology | rss | 科技商业 |
| Ars Technica | rss | 深度科技报道 |
| Hugging Face Blog | rss | 模型与开源生态 |
| 更多... | — | 见 `source_config.json` |

## 模型执行

通过 `llm_decider.py` → `openclaw_model_executor.mjs` 调用 OpenClaw 宿主已配置的模型注册表和鉴权存储。

| 阶段 | 模型 | 说明 |
|------|------|------|
| 粗筛 | MiniMax | 元数据筛选，低成本 |
| 初读 | MiniMax | 阅读卡片生成，保留广度 |
| 终判 | GPT54 | 最终 keep/drop，高质量判断 |

不在 skill 内配置 API Key，不维护 provider URL，不走独立模型环境变量。

## 测试

```bash
cd external-learning
python3 -m pytest tests/ -v
```

14 个测试全绿。

## 配置

信息源配置在 `modules/sources/source_config.json`，支持三种类型：

- `rss` — RSS/Atom feed
- `deepxiv` — arXiv 论文搜索
- `fetch` — 网页抓取

每个源可配置优先级（priority）、检查间隔（interval_hours）和关键词（queries）。

## 2026-04-27 更新

- `WORKSPACE_ROOT` 从硬编码改为 `runtime_config` 动态解析（content_fetcher / deepread / quality / gather_programmatic）
- 三模块统一路径体系（X-Memory / self-evolution / external-learning 共享 runtime_config）
- 新增深读筛选机制：≥8 分通过 proposal_bridge 进 self-evolution
- 新增 `minimax_screener.py` 粗筛层（元数据级，不读全文）
- 14 个测试全绿
