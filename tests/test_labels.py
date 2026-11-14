"""Bảng nhãn tay: xuất từ trace, giữ nhãn đã duyệt, tổng hợp chỉ từ cột của tác giả (src/labels.py)."""
import unittest

from src import labels as L

QUESTIONS = {
    "q1": {"id": "q1", "question": "Bao lâu?", "answerable": True, "expected_answer": "72 giờ",
           "gold": [{"source_id": "nd13", "page": 1, "evidence": "nội dung c2"}]},
    "q2": {"id": "q2", "question": "Ai?", "answerable": True, "expected_answer": "Bộ Công an",
           "gold": [{"source_id": "nd13", "page": 2, "evidence": "Bộ Công an"}]},
    "u1": {"id": "u1", "question": "Phạt bao nhiêu?", "answerable": False, "absence_reason": "không có mức phạt"},
}


def trace(qid, status, answer="", citations=(), chunks=()):
    return {"query_id": qid, "status": status, "answer": answer, "citations": list(citations),
            "final_context_chunks": [{"id": c, "source_id": "nd13", "page": 1, "text": f"nội dung {c}"} for c in chunks]}


TRACES = [
    trace("q1", "answered", "72 giờ [c1][c2].", ["c1", "c2"], ["c1", "c2"]),
    trace("q2", "abstain", "Không đủ bằng chứng."),
    trace("u1", "abstain", "Không có mức phạt."),
]


def review(rows, labels):
    """Giả lập tác giả điền cột nhãn chính thức."""
    for row, label in zip(rows, labels):
        row["label"], row["reason"] = str(label), "đã đọc"
    return rows


class ExportTest(unittest.TestCase):
    def test_answer_rows_one_per_question_with_kind(self):
        rows = L.answer_rows(QUESTIONS, TRACES, run="dense/dev")
        self.assertEqual([r["query_id"] for r in rows], ["q1", "q2", "u1"])
        self.assertEqual([r["kind"] for r in rows], ["grounded", "grounded", "abstention"])
        self.assertEqual(rows[0]["expected"], "72 giờ")
        self.assertEqual(rows[2]["expected"], "không có mức phạt")
        self.assertEqual(rows[0]["label"], "")

    def test_error_runs_get_no_label_row(self):
        rows = L.answer_rows(QUESTIONS, TRACES + [trace("q9", "error")], run="dense/dev")
        self.assertNotIn("q9", [r["query_id"] for r in rows])

    def test_citation_rows_only_for_answers_with_chunk_text(self):
        rows = L.citation_rows(TRACES, run="dense/dev")
        self.assertEqual([(r["query_id"], r["citation"]) for r in rows], [("q1", "c1"), ("q1", "c2")])
        self.assertEqual(rows[0]["chunk_text"], "nội dung c1")
        self.assertEqual(rows[0]["in_context"], "1")

    def test_merge_keeps_reviewed_labels_only_when_answer_unchanged(self):
        old = review(L.answer_rows(QUESTIONS, TRACES, run="dense/dev"), [2, 0, 1])
        old[0]["suggested_label"] = "2"
        changed = [trace("q1", "answered", "Khác [c1].", ["c1"], ["c1"])] + TRACES[1:]
        new = L.merge(old, L.answer_rows(QUESTIONS, changed, run="dense/dev"), L.ANSWER_KEY)
        self.assertEqual([r["label"] for r in new], ["", "0", "1"])

    def test_context_rows_for_answerable_questions_mark_evidence_chunks(self):
        rows = L.context_rows(QUESTIONS, TRACES, run="dense/test")
        self.assertEqual([r["query_id"] for r in rows], ["q1", "q2"])
        self.assertEqual(rows[0]["context_ids"], "c1; c2")
        self.assertEqual(rows[0]["evidence_ids"], "c2")
        self.assertEqual(rows[1]["evidence_ids"], "")
        self.assertIn("nd13 tr. 1", rows[0]["gold"])

    def test_merge_resets_context_label_when_context_changes(self):
        old = review(L.context_rows(QUESTIONS, TRACES, run="dense/test"), [2, 0])
        changed = [trace("q1", "answered", "72 giờ [c2].", ["c2"], ["c2"])] + TRACES[1:]
        new = L.merge(old, L.context_rows(QUESTIONS, changed, run="dense/test"), L.ANSWER_KEY)
        self.assertEqual([r["label"] for r in new], ["", "0"])

    def test_suggestions_fill_only_suggested_columns(self):
        rows = L.answer_rows(QUESTIONS, TRACES, run="dense/dev")
        L.apply_suggestions(rows, {("dense/dev", "q1"): ("2", "đủ ý")}, L.ANSWER_KEY)
        self.assertEqual((rows[0]["suggested_label"], rows[0]["suggested_reason"]), ("2", "đủ ý"))
        self.assertEqual(rows[0]["label"], "")


class SummaryTest(unittest.TestCase):
    def rows(self):
        answers = review(L.answer_rows(QUESTIONS, TRACES, run="dense/dev"), [2, 0, 1])
        for r, s in zip(answers, ["2", "0", "1"]):
            r["suggested_label"] = s
        answers[0]["suggested_label"] = "1"  # tác giả sửa gợi ý
        cites = review(L.citation_rows(TRACES, run="dense/dev"), [1, 0])
        for r in cites:
            r["suggested_label"] = "1"
        return answers, cites

    def test_summary_uses_author_labels(self):
        answers, cites = self.rows()
        s = L.summarize(answers, cites, run="dense/dev")
        self.assertEqual(s["grounded"]["levels"], {"0": 1, "1": 0, "2": 1})
        self.assertEqual(s["grounded"]["mean"], 1.0)
        self.assertEqual(s["grounded"]["N"], 2)
        self.assertEqual(s["abstention_correct"], {"n": 1, "N": 1})
        self.assertEqual(s["citations_valid"], {"n": 1, "N": 2})
        self.assertEqual(s["review"], {"rows": 5, "kept": 3, "changed": 2})

    def test_context_levels_reported_when_present(self):
        answers, cites = self.rows()
        context = review(L.context_rows(QUESTIONS, TRACES, run="dense/dev"), [2, 0])
        for r in context:
            r["suggested_label"] = r["label"]
        s = L.summarize(answers, cites, run="dense/dev", context=context)
        self.assertEqual(s["context"], {"levels": {"0": 1, "1": 0, "2": 1}, "N": 2})
        self.assertEqual(s["review"], {"rows": 7, "kept": 5, "changed": 2})
        self.assertNotIn("context", L.summarize(answers, cites, run="dense/dev"))

    def test_unreviewed_row_is_an_error(self):
        answers, cites = self.rows()
        answers[1]["label"] = ""
        with self.assertRaises(L.UnreviewedError):
            L.summarize(answers, cites, run="dense/dev")

    def test_label_out_of_range_is_an_error(self):
        answers, cites = self.rows()
        answers[0]["label"] = "3"
        with self.assertRaises(ValueError):
            L.summarize(answers, cites, run="dense/dev")

    def test_answerable_abstain_must_be_graded_zero(self):
        answers, cites = self.rows()
        answers[1]["label"] = "1"
        with self.assertRaises(ValueError):
            L.summarize(answers, cites, run="dense/dev")


if __name__ == "__main__":
    unittest.main()
