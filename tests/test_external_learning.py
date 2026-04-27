"""Tests for external-learning new architecture only."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "modules"))


class TestQuality(unittest.TestCase):
    def test_high_quality_note(self):
        from quality import score_note_quality

        note = {
            "核心内容": "- 方法A\n- 方法B\n- 方法C",
            "对我们的启发": "可以用在 evolution_strategy 模块",
            "关键数据": "准确率达 95%",
            "来源等级": "原文级",
            "二次验证": "交叉验证通过",
        }
        self.assertGreaterEqual(score_note_quality(note), 6.0)

    def test_low_quality_note(self):
        from quality import score_note_quality

        note = {
            "核心内容": "",
            "对我们的启发": "值得关注",
            "关键数据": "",
            "来源等级": "摘要级",
            "二次验证": "",
        }
        self.assertLess(score_note_quality(note), 6.0)


class TestGatherProgrammatic(unittest.TestCase):
    def test_build_reason_uses_structural_signals(self):
        from gather_programmatic import build_reason

        reason = build_reason(
            "Guardrails Beat Guidance in Coding Agents",
            "We present a benchmark and evaluation for agent behavior.",
            "https://arxiv.org/abs/2604.11088",
            {"id": "arxiv-deepxiv", "type": "deepxiv", "priority": 1},
            9.2,
        )
        self.assertIn("论文源", reason)
        self.assertIn("综合分", reason)

    def test_dedupe_candidates_keeps_highest_score(self):
        from gather_programmatic import dedupe_candidates

        deduped = dedupe_candidates([
            {"url": "https://example.com/a", "score": 7.0, "title": "low"},
            {"url": "https://example.com/a/", "score": 9.0, "title": "high"},
            {"url": "https://example.com/b", "score": 8.0, "title": "other"},
        ])
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["title"], "high")

    def test_score_item_prefers_research_structure_over_newsletter(self):
        from gather_programmatic import score_item

        research_score, _ = score_item(
            "AgentWebBench: Benchmarking Multi-Agent Coordination in Agentic Web",
            "We present a benchmark and evaluate coordination with detailed results.",
            "https://arxiv.org/abs/2604.10938",
            {"id": "arxiv-deepxiv", "type": "deepxiv", "priority": 1},
        )
        digest_score, _ = score_item(
            "Weekly AI Newsletter #42",
            "This week in AI news and links.",
            "https://example.com/newsletter",
            {"id": "misc", "type": "rss", "priority": 3},
        )
        self.assertGreater(research_score, digest_score)

    def test_write_candidates_markdown_includes_reason(self):
        import gather_programmatic

        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = gather_programmatic.LEARNING_DIR
            original_update = gather_programmatic.update_heartbeat_state
            gather_programmatic.LEARNING_DIR = Path(tmpdir)
            gather_programmatic.update_heartbeat_state = lambda source_id: None
            try:
                gather_programmatic.write_candidates_markdown(
                    "demo",
                    "Demo Source",
                    [{
                        "title": "Test",
                        "url": "https://example.com",
                        "score": 8.5,
                        "reason": "论文源; 结构信号强",
                        "published": "2026-04-19",
                    }],
                    "2026-04-19",
                )
                content = Path(tmpdir, "candidates-demo-2026-04-19.md").read_text(encoding="utf-8")
                self.assertIn("理由", content)
                self.assertIn("论文源", content)
            finally:
                gather_programmatic.LEARNING_DIR = original_dir
                gather_programmatic.update_heartbeat_state = original_update


class TestDecider(unittest.TestCase):
    @patch("decider.screen_candidates")
    @patch("decider.enrich_candidates_with_content")
    @patch("decider.generate_reading_cards")
    @patch("llm_decider.run_final_judgment")
    def test_filter_for_deep_read_runs_final_judgment(self, mock_run_final_judgment, mock_generate_reading_cards, mock_enrich, mock_screen):
        from deepread import filter_for_deep_read

        screened_item = {
            "title": "Self-Evolving LLM Memory Extraction Across Heterogeneous Tasks",
            "description": "We propose a memory extraction method and evaluate it across tasks.",
            "reason": "论文源; 结构信号强",
            "url": "https://arxiv.org/abs/2604.11610",
            "score": 7.6,
            "screen_score": 8.7,
            "screen_decision": "keep",
        }
        mock_screen.return_value = [screened_item]
        mock_enrich.return_value = [{**screened_item, "content_text": "full text", "content_source": "arxiv_pdf", "content_chars": 12000}]
        mock_generate_reading_cards.return_value = [
            {
                "title": "Self-Evolving LLM Memory Extraction Across Heterogeneous Tasks",
                "description": "We propose a memory extraction method and evaluate it across tasks.",
                "url": "https://arxiv.org/abs/2604.11610",
                "score": 7.6,
                "reader_score": 8.8,
                "reader_summary": "关于跨任务记忆提取的方法论文",
                "reader_rationale": "和 Agent 记忆主线强相关",
            }
        ]
        mock_run_final_judgment.return_value = {
            "items": [
                {"id": 1, "final_score": 9.1, "decision": "keep", "rationale": "贴主线"},
            ]
        }

        items = [
            {
                "title": "Self-Evolving LLM Memory Extraction Across Heterogeneous Tasks",
                "description": "We propose a memory extraction method and evaluate it across tasks.",
                "reason": "论文源; 结构信号强",
                "url": "https://arxiv.org/abs/2604.11610",
                "score": 7.6,
            }
        ]
        selected = filter_for_deep_read(items, min_score=8.0, max_count=5)
        self.assertEqual(len(selected), 1)
        self.assertIn("Memory Extraction", selected[0]["title"])
        self.assertEqual(selected[0]["final_score"], 9.1)

    def test_apply_llm_judgment_uses_final_scores(self):
        from decider import apply_llm_judgment

        items = [
            {"title": "A", "url": "https://a.com", "score": 8.0, "reader_score": 8.2},
            {"title": "B", "url": "https://b.com", "score": 9.0, "reader_score": 9.1},
        ]
        judgment = {
            "items": [
                {"id": 1, "final_score": 9.4, "decision": "keep", "rationale": "更贴主线"},
                {"id": 2, "final_score": 7.2, "decision": "drop", "rationale": "泛资讯"},
            ]
        }
        selected = apply_llm_judgment(items, judgment, threshold=8.0, max_count=5)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["title"], "A")


class TestMiniMaxReader(unittest.TestCase):
    @patch("minimax_reader.run_screen_judgment")
    def test_generate_reading_cards_keeps_reader_fields(self, mock_run_screen_judgment):
        from minimax_reader import generate_reading_cards

        mock_run_screen_judgment.return_value = {
            "items": [
                {
                    "id": 1,
                    "decision": "keep",
                    "reader_score": 8.4,
                    "topic": "Agent memory",
                    "summary": "初读认为这是记忆方向的研究条目",
                    "model_relevance": "high",
                    "next_action": "deepread",
                    "rationale": "与主线直接相关",
                }
            ]
        }

        cards = generate_reading_cards([
            {
                "title": "Self-Evolving LLM Memory Extraction",
                "url": "https://arxiv.org/abs/2604.11610",
                "description": "memory extraction across tasks",
                "score": 7.5,
            }
        ])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["reader_model_relevance"], "high")
        self.assertEqual(cards[0]["reader_next_action"], "deepread")


class TestDeepReadRelevance(unittest.TestCase):
    def test_classify_model_relevance_positive(self):
        from deepread import classify_model_relevance

        result = classify_model_relevance({
            "title": "Guardrails Beat Guidance in Coding Agents",
            "description": "Evaluation study for LLM agents and benchmarks",
            "reason": "研究型条目; 评测相关",
        })
        self.assertEqual(result["模型相关性"], "高")
        self.assertEqual(result["建议优先级"], "P1")

    def test_classify_model_relevance_negative(self):
        from deepread import classify_model_relevance

        result = classify_model_relevance({
            "title": "Why Japan has such good railways",
            "description": "Rail infrastructure and transport policy",
            "reason": "基础设施观察",
        })
        self.assertEqual(result["模型相关性"], "低")
        self.assertEqual(result["建议优先级"], "skip")


class TestGatherHelpers(unittest.TestCase):
    def test_get_pending_sources(self):
        from gather import get_pending_sources
        pending = get_pending_sources(force_all=True)
        self.assertGreater(len(pending), 0)

    def test_generate_evolution_proposals_threshold(self):
        from gather import generate_evolution_proposals

        items = [
            {"source": "arxiv", "url": "https://arxiv.org/abs/1234.5678", "score": 9.6, "reason": "paper"},
            {"source": "github", "url": "https://github.com/demo/repo", "score": 8.6, "reason": "repo"},
            {"source": "hn", "url": "https://news.ycombinator.com/item?id=1", "score": 7.9, "reason": "skip"},
        ]
        proposals = generate_evolution_proposals(items)
        self.assertEqual(len(proposals), 2)
        self.assertEqual(proposals[0]["priority"], "P0")
        self.assertEqual(proposals[1]["priority"], "P1")

    @patch("gather.push_to_evolution")
    @patch("gather.write_candidates_markdown")
    @patch("gather._fetch_source")
    def test_gather_is_canonical_entry(self, mock_fetch_source, mock_write_candidates, mock_push):
        from gather import gather

        mock_fetch_source.return_value = [
            {"title": "demo", "url": "https://example.com", "score": 9.0, "reason": "desc", "source": "github", "published": "2026-04-14"}
        ]

        results = gather(force_all=True, only_new=False)
        self.assertIsInstance(results, dict)
        mock_write_candidates.assert_called()
        mock_push.assert_called_once()


if __name__ == "__main__":
    unittest.main()
