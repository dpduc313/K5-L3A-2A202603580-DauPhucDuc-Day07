"""Metric retrieval và agent (src/metrics.py): mẫu số, câu thiếu evidence, lỗi."""
import unittest

from src import metrics as M

GOLD = [{"source_id": "nd13", "page": 1, "evidence": "72 giờ"}]


def q(id, answerable=True, split="dev"):
    base = {"id": id, "split": split, "question": "?", "answerable": answerable}
    return {**base, "gold": GOLD, "expected_answer": "72 giờ"} if answerable else base


def c(id, text, page=1):
    return {"id": id, "text": text, "source_id": "nd13", "source": "nd13.pdf", "page": page, "metadata": {}}


class RetrievalMetricTest(unittest.TestCase):
    def test_hit_at_1_and_3_exclude_unanswerable(self):
        rows = [M.score_retrieval(q("q1"), [c("x", "khác"), c("y", "xóa trong 72 giờ")]),
                M.score_retrieval(q("q2"), [c("y", "xóa trong 72 giờ")]),
                M.score_retrieval(q("u1", answerable=False), [c("x", "khác")])]
        s = M.summarize_retrieval(rows)
        self.assertEqual((s["hit1"]["n"], s["hit1"]["N"]), (1, 2))
        self.assertEqual((s["hit3"]["n"], s["hit3"]["N"]), (2, 2))

    def test_hit_only_counts_top3(self):
        ranked = [c("a", "x"), c("b", "x"), c("d", "x"), c("e", "72 giờ")]
        self.assertFalse(M.score_retrieval(q("q1"), ranked)["hit3"])


class AgentMetricTest(unittest.TestCase):
    def trace(self, qid, status, context, searches=1, cost=0.001, seconds=2.0):
        return {"query_id": qid, "status": status, "final_context_chunks": context, "searches": searches,
                "cost_usd": cost, "seconds": seconds}

    def test_context_rate_tool_use_and_errors(self):
        qs = [q("q1"), q("q2"), q("q3"), q("u1", answerable=False)]
        traces = [self.trace("q1", "answered", [c("y", "trong 72 giờ")]),
                  self.trace("q2", "abstain", [c("x", "khác")], searches=2),
                  self.trace("q3", "error", [], searches=0),
                  self.trace("u1", "abstain", [c("x", "khác")])]
        s = M.summarize_agent(qs, traces)
        self.assertEqual((s["context_evidence"]["n"], s["context_evidence"]["N"]), (1, 3))
        self.assertEqual(s["errors"], 1)
        self.assertEqual((s["tool_use"]["n"], s["tool_use"]["N"]), (3, 3))
        self.assertEqual(s["searches_distribution"], {"1": 2, "2": 1})
        self.assertEqual((s["abstained_unanswerable"]["n"], s["abstained_unanswerable"]["N"]), (1, 1))
        self.assertEqual((s["false_abstention"]["n"], s["false_abstention"]["N"]), (1, 3))
        self.assertAlmostEqual(s["cost_usd"]["total"], 0.004)

    def test_missing_trace_is_an_error(self):
        with self.assertRaises(ValueError):
            M.summarize_agent([q("q1")], [])


if __name__ == "__main__":
    unittest.main()
