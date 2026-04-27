# External Learning v3

`external-learning` 定期从外部信息源采集技术情报，走固定四段链路：

1. 程序化抓取候选
2. MiniMax 初读生成 reading cards
3. GPT54 终判 keep/drop
4. 主 Agent 深读、验证、沉淀笔记

## 目录结构

```text
external-learning/
├── SKILL.md
├── README.md
├── modules/
│   ├── __init__.py
│   ├── gather.py
│   ├── gather_programmatic.py
│   ├── minimax_reader.py
│   ├── decider.py
│   ├── deepread.py
│   ├── quality.py
│   └── sources/
│       ├── __init__.py
│       └── source_config.json
└── tests/
    └── test_external_learning.py
```

## 使用

```bash
cd /root/.openclaw/skills/external-learning/modules
python3 gather.py --force
```

```python
from modules.gather import gather, merge_all_candidates
from modules.deepread import filter_for_deep_read, deep_read_batch, save_notes

results = gather(force_all=False)
candidates = merge_all_candidates()
selected = filter_for_deep_read(candidates, min_score=8.0, max_count=5)
notes = deep_read_batch(selected)
save_notes(notes)
```

## 当前代码边界

- `gather.py`: 采集入口
- `gather_programmatic.py`: RSS / DeepXiv / GitHub Trending 抓取实现
- `minimax_reader.py`: 初读卡片生成
- `decider.py`: GPT54 最终判断
- `deepread.py`: 深读笔记模板与保存
- `quality.py`: 笔记质量与二次验证
- `source_config.json`: 信息源配置

## 模型执行

`llm_decider.py` 通过 `modules/openclaw_model_executor.mjs` 调用 OpenClaw 宿主已配置的模型注册表和鉴权存储。

固定模型别名：

- 初读：`Minimax`
- 终判：`GPT54`

不在 skill 内配置 key、不读取独立模型环境变量、不维护 provider URL。


## 信息源类型

`source_config.json` 里的 `type` 支持：

- `rss`
- `deepxiv`
- `fetch`

新增其他类型时，先扩展 `gather_programmatic.py`。

## 测试

```bash
cd /root/.openclaw/skills/external-learning
python3 -m unittest discover -s tests -p 'test_external_learning.py'
```
