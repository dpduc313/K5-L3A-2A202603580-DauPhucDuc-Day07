"""Phần nâng cao: ghép dấu cách, chunk theo mục, kiểm tra benchmark, metric, cấu hình. Không cần DB hay API."""
import unittest

from src.advanced import benchmark as B
from src.advanced import chunks as K
from src.advanced import experiment as E
from src.advanced import extract as X
from src.advanced import metrics as M


def glyph(c, x0, x1, y0=0, y1=10):
    return {"c": c, "bbox": (x0, y0, x1, y1)}


class SpacingTest(unittest.TestCase):
    def test_gap_wider_than_ratio_becomes_space(self):
        # "Đồ" và "thị" cách nhau 3pt (> 0.15 × 10pt), không có glyph dấu cách
        chars = [glyph("Đ", 0, 5), glyph("ồ", 5, 10), glyph("t", 13, 16), glyph("h", 16, 21), glyph("ị", 21, 24)]
        self.assertEqual(X.chars_text(chars), "Đồ thị")

    def test_kerning_gap_is_not_a_space(self):
        chars = [glyph("a", 0, 5), glyph("b", 5.5, 10)]
        self.assertEqual(X.chars_text(chars), "ab")

    def test_glued_tokens_flags_two_tone_marks(self):
        self.assertEqual(X.glued_tokens("dữliệu được dùng"), ["dữliệu"])
        self.assertEqual(X.glued_tokens("dữ liệu BatchNormalization"), [])


TOC = [{"page": 47, "y": 80, "level": 2, "title": "3 Linear regression"},
       {"page": 47, "y": 200, "level": 3, "title": "3.1 Bài toán"},
       {"page": 48, "y": 450, "level": 3, "title": "3.2 Thiết lập công thức"}]


def block(y, text):
    return {"bbox": [85, y, 510, y + 20], "text": text, "size": 11, "bold": False}


class ChunkTest(unittest.TestCase):
    def test_section_at_uses_last_heading_before_position(self):
        self.assertEqual(K.section_at(TOC, 48, 300), ["3 Linear regression", "3.1 Bài toán"])
        self.assertEqual(K.section_at(TOC, 48, 460), ["3 Linear regression", "3.2 Thiết lập công thức"])
        self.assertEqual(K.section_at(TOC, 10, 100), [K.FRONT_MATTER])

    def test_text_never_crosses_section_and_table_figure_are_own_chunks(self):
        pages = [
            {"page": 47, "blocks": [block(210, "đoạn một"), block(300, "đoạn hai")],
             "tables": [{"id": "tab-p047-1", "bbox": [200, 400, 380, 500], "caption": None,
                         "rows": [["a", "b"], ["1", "2"]], "markdown": "| a | b |\n|---|---|\n| 1 | 2 |"}],
             "figures": []},
            {"page": 48, "blocks": [block(100, "đoạn ba"), block(470, "đoạn bốn")], "tables": [],
             "figures": [{"id": "fig-3.1", "label": "Hình 3.1", "caption": "Hình 3.1: Đồ thị", "bbox": [85, 200, 510, 400],
                          "caption_bbox": [180, 410, 400, 425], "crop": "data/advanced/figures/fig-3.1.jpg"}]},
        ]
        built = K.build(pages, TOC, {"fig-3.1": "biểu đồ phân tán"}, lambda s: len(s.split()))
        by_id = {c["id"]: c for c in built}
        text = [c for c in built if c["metadata"]["kind"] == "text"]
        self.assertEqual([c["id"] for c in text], ["dlcb-t-p047-1", "dlcb-t-p048-1"])
        self.assertIn("đoạn ba", text[0]["text"])  # cùng mục 3.1, nối qua trang
        self.assertEqual(text[0]["metadata"]["pages"], [47, 48])
        self.assertIn("đoạn bốn", text[1]["text"])  # mục 3.2 là chunk mới
        table = by_id["dlcb-tab-p047-1"]
        self.assertIn("Đoạn văn ngay trước: đoạn hai", table["text"])
        self.assertTrue(table["locator"].startswith("trang 47, bảng, vùng"))
        fig = by_id["dlcb-fig-3.1"]
        self.assertIn("biểu đồ phân tán", fig["text"])
        self.assertEqual(fig["metadata"]["crop"], "data/advanced/figures/fig-3.1.jpg")
        self.assertIn("vùng (85, 200, 510, 425)", fig["locator"])  # hình + caption


def chunk(id, kind, pages, text=""):
    return {"id": id, "text": text, "metadata": {"kind": kind, "pages": pages}}


def question(id, split, group, evidence=None, **kw):
    q = {"id": id, "split": split, "group": group, "question": "?", "reason": "r"}
    if group == "unanswerable":
        q |= {"expected_behavior": "search_and_abstain", "absence_reason": "x",
              "absence_check": {"results": [{"pattern": "zzz", "hits": 0, "pages": []}]}}
    else:
        q |= {"expected_answer": "a", "evidence": evidence or []}
    return q | kw


class BenchmarkTest(unittest.TestCase):
    CHUNKS = [chunk("t1", "text", [5], "Hệ số p nên ở khoảng [0.2, 0.5]"), chunk("f1", "figure", [6]),
              chunk("b1", "table", [7], "| 7 | Sneaker |")]

    def errors(self, qs):
        return B.verify(qs, self.CHUNKS, {5: "", 6: "", 7: ""})[0]

    def test_quote_must_be_inside_chunk(self):
        q = question("x", "dev", "text", [{"page": 5, "kind": "text", "chunk_id": "t1", "locator": "l", "quote": "p = 0.9"}])
        self.assertTrue(any("quote không nằm trọn" in e for e in self.errors([q])))

    def test_chart_question_needs_figure_evidence(self):
        q = question("x", "dev", "chart", [{"page": 5, "kind": "text", "chunk_id": "t1", "locator": "l",
                                            "quote": "Hệ số p nên ở khoảng"}])
        self.assertTrue(any("không có evidence loại figure" in e for e in self.errors([q])))

    def test_multihop_needs_two_chunks(self):
        q = question("x", "dev", "multihop", [{"page": 6, "kind": "figure", "chunk_id": "f1", "locator": "l"}])
        self.assertTrue(any("ít nhất 2 chunk" in e for e in self.errors([q])))

    def test_same_evidence_in_dev_and_test_is_an_error(self):
        ev = [{"page": 7, "kind": "table", "chunk_id": "b1", "locator": "l", "quote": "| 7 | Sneaker |"}]
        errs = self.errors([question("d", "dev", "table", ev), question("t", "test", "table", ev)])
        self.assertTrue(any("cùng một bộ evidence" in e for e in errs))

    def test_test_split_minimums(self):
        errs = self.errors([question("u", "test", "unanswerable")])
        self.assertIn("test nhóm table: 0 < 6", errs)
        self.assertIn("test nhóm unanswerable: 1 < 6", errs)

    def test_absence_regex_rechecked(self):
        q = question("u", "dev", "unanswerable")
        q["absence_check"]["results"][0] = {"pattern": "sneaker", "hits": 0, "pages": []}
        errs = B.verify([q], self.CHUNKS, {7: "| 7 | sneaker |"})[0]
        self.assertTrue(any("khớp 1 lần" in e for e in errs))


class MetricsTest(unittest.TestCase):
    Q = {"id": "q", "group": "multihop", "evidence": [{"chunk_id": "a", "kind": "text"}, {"chunk_id": "f", "kind": "figure"}]}

    def trace(self, status, citations, context, viewed=()):
        return {"status": status, "citations": citations, "final_context_ids": context, "viewed_figures": list(viewed),
                "searches": 1, "seconds": 1.0, "cost_usd": 0.001}

    def test_auto_pass_needs_all_evidence_cited(self):
        self.assertFalse(M.score_agent(self.Q, self.trace("answered", ["a"], ["a", "f"]))["auto_pass"])
        row = M.score_agent(self.Q, self.trace("answered", ["a", "f"], ["a", "f"], viewed=["f"]))
        self.assertTrue(row["auto_pass"])
        self.assertTrue(row["viewed_gold"])

    def test_unanswerable_passes_only_on_abstain(self):
        u = {"id": "u", "group": "unanswerable"}
        self.assertTrue(M.score_agent(u, self.trace("abstain", [], []))["auto_pass"])
        self.assertFalse(M.score_agent(u, self.trace("answered", ["a"], ["a"]))["auto_pass"])
        self.assertFalse(M.score_agent(u, self.trace("error", [], []))["auto_pass"])


class ConfigTest(unittest.TestCase):
    def test_each_variant_changes_one_factor(self):
        for name, cfg in E.CONFIGS.items():
            if "base" not in cfg:
                continue
            base, mine = E.settings(cfg["base"]), E.settings(name)
            changed = {k for k in mine if k not in ("role", "base") and mine.get(k) != base.get(k)}
            self.assertEqual(len(changed), 1, f"{name} đổi {changed}")

    def test_viewer_only_for_figure_chunks(self):
        self.assertIsNone(E.figure_viewer({"metadata": {"kind": "text"}}))


if __name__ == "__main__":
    unittest.main()
