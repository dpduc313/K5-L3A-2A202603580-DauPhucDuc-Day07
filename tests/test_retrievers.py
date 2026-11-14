"""Hành vi của BM25, RRF và filter (src/retrievers.py); dense cần database nên không test ở đây."""
import unittest

from src import retrievers as R


def chunk(id, text, chapters=("Chương I",), source_id="nd13", page=1):
    return {"id": id, "text": text, "source_id": source_id, "source": f"{source_id}.pdf", "page": page,
            "metadata": {"chapters": list(chapters), "sections": [], "language": "vi", "document_type": "decree"}}


CHUNKS = [
    chunk("a", "Dữ liệu cá nhân được xóa trong 72 giờ sau khi có yêu cầu."),
    chunk("b", "Bên Kiểm soát dữ liệu thông báo cho Bộ Công an.", chapters=["Chương II"]),
    chunk("c", "Trẻ em từ đủ 7 tuổi trở lên phải đồng ý."),
]


class TokenizeTest(unittest.TestCase):
    def test_syllables_and_adjacent_bigrams(self):
        self.assertEqual(R.tokenize("Dữ liệu cá-nhân"), ["dữ", "liệu", "cá", "nhân", "dữ_liệu", "liệu_cá", "cá_nhân"])


class BM25Test(unittest.TestCase):
    def test_ranks_matching_chunk_first_with_rank_and_method(self):
        res = R.BM25(CHUNKS).search("xóa dữ liệu trong bao lâu", filters=None, top_k=2)
        self.assertEqual(res[0]["id"], "a")
        self.assertEqual([r["rank"] for r in res], list(range(1, len(res) + 1)))
        self.assertEqual(res[0]["method"], "bm25")

    def test_filter_applies_before_ranking(self):
        res = R.BM25(CHUNKS).search("xóa dữ liệu", filters={"chapter": "Chương II"}, top_k=5)
        self.assertEqual([r["id"] for r in res], ["b"])

    def test_no_overlap_returns_nothing(self):
        self.assertEqual(R.BM25(CHUNKS).search("transformer attention", filters=None, top_k=5), [])


class FakeRetriever:
    def __init__(self, name, ids):
        self.name, self.ids = name, ids

    def search(self, query, *, filters, top_k):
        self.filters = filters
        return [{**chunk(i, i), "score": 1.0, "rank": n, "method": self.name} for n, i in enumerate(self.ids[:top_k], 1)]


class HybridTest(unittest.TestCase):
    def test_rrf_scores(self):
        fused = R.rrf({"dense": ["x", "y"], "bm25": ["y", "z"]}, k=60)
        self.assertEqual([i for i, _, _ in fused], ["y", "x", "z"])
        self.assertAlmostEqual(fused[0][1], 1 / 62 + 1 / 61)
        self.assertEqual(fused[0][2], {"dense": 2, "bm25": 1})

    def test_hybrid_passes_filter_to_both_and_keeps_component_ranks(self):
        dense, bm25 = FakeRetriever("dense", ["x", "y"]), FakeRetriever("bm25", ["y", "z"])
        res = R.Hybrid(dense, bm25).search("q", filters={"chapter": "Chương I"}, top_k=2)
        self.assertEqual([r["id"] for r in res], ["y", "x"])
        self.assertEqual(dense.filters, {"chapter": "Chương I"})
        self.assertEqual(bm25.filters, {"chapter": "Chương I"})
        self.assertEqual(res[0]["components"], {"dense": 2, "bm25": 1})
        self.assertEqual(res[0]["method"], "hybrid")


class DenseFilterSqlTest(unittest.TestCase):
    def test_filter_becomes_parameterised_where_clause(self):
        where, params = R.filter_sql({"chapter": "Chương II", "language": "vi", "source_id": "nd13"})
        self.assertIn("%(chapter)s = ANY(chapters)", where)
        self.assertIn("language = %(language)s", where)
        self.assertIn("document_id = %(source_id)s", where)
        self.assertEqual(params["chapter"], "Chương II")

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            R.filter_sql({"author": "x"})


if __name__ == "__main__":
    unittest.main()
