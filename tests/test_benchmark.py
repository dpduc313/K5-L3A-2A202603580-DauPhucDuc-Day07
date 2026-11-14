"""Kiểm tra định nghĩa hit, filter và kiểm tra bộ câu hỏi (src/benchmark.py)."""
import unittest

from src import benchmark as B
from src.lab_config import normalize


def chunk(id="c1", text="Yêu cầu hoàn tiền được xử lý trong 7 ngày làm việc.", source_id="doc", page=1, **meta):
    metadata = {"chapters": ["Chương I"], "sections": ["Điều 1"], "language": "vi", "document_type": "decree"}
    metadata.update(meta)
    return {"id": id, "text": text, "source_id": source_id, "source": f"{source_id}.pdf", "page": page,
            "metadata": metadata}


def answerable(id="q1", split="dev", evidence="xử lý trong 7 ngày", page=1, flt=None):
    q = {"id": id, "split": split, "question": "Bao lâu?", "answerable": True,
         "expected_answer": "7 ngày", "gold": [{"source_id": "doc", "page": page, "evidence": evidence}]}
    if flt:
        q["filter"] = flt
    return q


class NormalizeTest(unittest.TestCase):
    def test_markdown_escape_and_spacing_do_not_break_match(self):
        # Lỗi q15 của Day 6: evidence chép từ Markdown có `warmup\_steps`.
        self.assertEqual(normalize("warmup\\_steps  =\n4000"), normalize("warmup_steps = 4000"))

    def test_unicode_forms_match(self):
        self.assertEqual(normalize("Nghì"), normalize("Nghì"))


class HitTest(unittest.TestCase):
    def test_hit_needs_same_source_page_and_contained_evidence(self):
        gold = {"source_id": "doc", "page": 1, "evidence": "xử lý trong 7 ngày"}
        self.assertTrue(B.contains_evidence(chunk(), gold))
        self.assertFalse(B.contains_evidence(chunk(page=2), gold))
        self.assertFalse(B.contains_evidence(chunk(source_id="other"), gold))
        self.assertFalse(B.contains_evidence(chunk(text="Hoàn tiền trong 7 ngày."), gold))

    def test_day6_chunk_keeps_filter_metadata(self):
        row = {"chunk_id": "nd13-heading-0001", "document_id": "nd13", "source": "nd13.pdf", "page": 5,
               "text": "x", "start": 0, "chapter": "Chương I", "section": "Điều 4", "chapters": ["Chương I"],
               "sections": ["Điều 4"], "language": "vi", "document_type": "decree", "chunking": "heading",
               "chars": 1, "tokens": 1, "text_sha256": "h"}
        c = B.to_day7_chunk(row)
        self.assertEqual((c["id"], c["source_id"]), ("nd13-heading-0001", "nd13"))
        self.assertEqual(c["metadata"]["chapters"], ["Chương I"])


class FilterTest(unittest.TestCase):
    def test_chapter_matches_any_chapter_the_chunk_spans(self):
        c = chunk(chapters=["Chương I", "Chương II"])
        self.assertTrue(B.satisfies(c, {"chapter": "Chương II"}))
        self.assertFalse(B.satisfies(c, {"chapter": "Chương III"}))
        self.assertTrue(B.satisfies(c, None))

    def test_unknown_filter_key_is_rejected(self):
        with self.assertRaises(ValueError):
            B.satisfies(chunk(), {"author": "x"})


class VerifyTest(unittest.TestCase):
    def full_set(self):
        qs = [answerable(f"d{i}") for i in range(15)] + [answerable(f"t{i}", "test") for i in range(5)]
        for i, split in enumerate(["dev", "dev", "test", "test"]):
            qs.append({"id": f"u{i}", "split": split, "question": "Phạt bao nhiêu?", "answerable": False,
                       "expected_behavior": "search_and_abstain", "absence_reason": "không có",
                       "absence_check": {"source_id": "doc", "results": [{"pattern": "phạt", "hits": 0, "pages": []}]}})
        return qs

    pages = [{"document_id": "doc", "page": 1, "text": "Yêu cầu hoàn tiền được xử lý trong 7 ngày làm việc."}]

    def test_valid_set_has_no_errors(self):
        self.assertEqual(B.verify(self.full_set(), [chunk()], self.pages), [])

    def test_reports_missing_minimum_and_unresolved_gold(self):
        qs = self.full_set()[1:]
        qs[0] = answerable("d1", evidence="không có trong chunk")
        errors = B.verify(qs, [chunk()], self.pages)
        self.assertTrue(any("dev có evidence: 14 < 15" in e for e in errors), errors)
        self.assertTrue(any("không nằm trọn" in e for e in errors), errors)

    def test_filter_that_excludes_gold_chunk_is_an_error(self):
        qs = self.full_set()
        qs[0] = answerable("d0", flt={"chapter": "Chương IX"})
        self.assertTrue(any("không thỏa filter" in e for e in B.verify(qs, [chunk()], self.pages)))

    def test_absence_check_is_recounted(self):
        qs = self.full_set()
        qs[-1]["absence_check"]["results"][0]["pattern"] = "hoàn tiền"
        self.assertTrue(any("giờ khớp 1 lần" in e for e in B.verify(qs, [chunk()], self.pages)))


if __name__ == "__main__":
    unittest.main()
