"""Lệnh demo (src/demo.py): chọn đúng 3 loại ví dụ và in đủ trace để kiểm chứng."""
import json
import unittest

from src import demo as D
from src import lab_config as C


def trace():
    return {"query_id": "q10", "status": "answered", "answer": "72 giờ [c1].", "citations": ["c1"],
            "final_context_ids": ["c1", "c2"], "final_context_tokens": 120, "searches": 1, "seconds": 2.5,
            "cost_usd": 0.0007, "error": None,
            "events": [{"event": "search", "query": "thời hạn xóa", "filter": None,
                        "results": [{"id": "c1", "source_id": "nd13", "page": 14, "score": 0.71, "rank": 1}]}]}


class DemoTest(unittest.TestCase):
    def test_live_examples_are_one_answerable_and_one_unanswerable_dev_question(self):
        qs = {q["id"]: q for q in json.loads(C.QUESTIONS.read_text("utf-8"))}
        kinds = [(qs[i]["split"], qs[i]["answerable"]) for i in D.LIVE_EXAMPLES]
        self.assertEqual(kinds, [("dev", True), ("dev", False)])

    def test_recorded_error_comes_from_a_saved_dev_trace_with_a_label_below_full(self):
        example = D.recorded_error()
        self.assertEqual(example["trace"]["query_id"], D.ERROR_EXAMPLE[1])
        self.assertIn(example["label"]["label"], {"0", "1"})

    def test_render_shows_searches_context_answer_and_citations(self):
        text = D.render(trace())
        for part in ("thời hạn xóa", "c1", "nd13 tr. 14", "answered", "72 giờ [c1].", "120 token", "$0.00070"):
            self.assertIn(part, text)


if __name__ == "__main__":
    unittest.main()
