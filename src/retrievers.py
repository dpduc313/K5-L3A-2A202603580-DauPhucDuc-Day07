"""Ba phương pháp retrieval trên cùng corpus (129 chunk heading của Day 6).

- `Dense`: embed query bằng `embeddinggemma-2` qua Perrier (có prefix query, đúng như lúc Day 6
  embed tài liệu), cosine exact trên `lab_chunks` trong pgvector. Phần SQL lấy từ
  src/evaluate.py của Day 6.
- `BM25`: viết bằng Python trên `data/chunks.json`. Tách từ: `lab_config.normalize`, âm tiết
  `\\w+` cộng bigram âm tiết liền kề (bắt từ ghép tiếng Việt: "dữ liệu", "cá nhân").
- `Hybrid`: RRF (k = 60) của top-20 dense và top-20 BM25.

Mọi phương pháp áp filter TRƯỚC khi xếp hạng, và trả về cùng một dạng kết quả: các trường
của chunk (id, text, source_id, source, page, metadata) cộng `score`, `rank`, `method`.
Lỗi embedding hoặc vector store được nâng thành `RetrievalError` kèm nơi xảy ra, không
thay bằng kết quả giả.
"""

import json
import math
import re
from collections import Counter

from src import lab_config as C
from src.benchmark import FILTER_EXACT_KEYS, FILTER_LIST_KEYS, satisfies

RRF_K = 60
HYBRID_DEPTH = 20


class RetrievalError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage


def load_chunks() -> list[dict]:
    return json.loads(C.CHUNKS.read_text("utf-8"))


def result(chunk: dict, score: float, rank: int, method: str, **extra) -> dict:
    return {**chunk, "score": float(score), "rank": rank, "method": method, **extra}


# --- BM25 ------------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    syllables = re.findall(r"\w+", C.normalize(text))
    return syllables + [f"{a}_{b}" for a, b in zip(syllables, syllables[1:])]


class BM25:
    name = "bm25"

    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.tf = [Counter(tokenize(c["text"])) for c in chunks]
        self.length = [sum(t.values()) for t in self.tf]
        self.avg_length = sum(self.length) / len(self.length)
        df = Counter(term for t in self.tf for term in t)
        n = len(chunks)
        # Biến thể idf không âm (Lucene): từ xuất hiện ở hơn nửa corpus vẫn đóng góp ít, không trừ điểm.
        self.idf = {term: math.log(1 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()}

    def score(self, i: int, terms: set[str]) -> float:
        tf, norm = self.tf[i], self.k1 * (1 - self.b + self.b * self.length[i] / self.avg_length)
        return sum(self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm) for t in terms if t in tf)

    def search(self, query: str, *, filters: dict | None, top_k: int) -> list[dict]:
        terms = set(tokenize(query))
        scored = [(self.score(i, terms), c) for i, c in enumerate(self.chunks) if satisfies(c, filters)]
        ranked = sorted(((s, c) for s, c in scored if s > 0), key=lambda x: (-x[0], x[1]["id"]))[:top_k]
        return [result(c, s, rank, self.name) for rank, (s, c) in enumerate(ranked, 1)]


# --- Dense -----------------------------------------------------------------------------

SEARCH_SQL = """
SELECT chunk_id, 1 - (embedding <=> %(q)s::vector) AS score
FROM {table}
WHERE chunking = %(chunking)s {where}
ORDER BY embedding <=> %(q)s::vector, chunk_id
LIMIT %(k)s
"""


def filter_sql(filters: dict | None) -> tuple[str, dict]:
    """Điều kiện WHERE có tham số cho filter; cùng ngữ nghĩa với `benchmark.satisfies`."""
    where, params = "", {}
    for key, value in (filters or {}).items():
        if key in FILTER_LIST_KEYS:
            where += f" AND %({key})s = ANY({FILTER_LIST_KEYS[key]})"
        elif key == "source_id":
            where += " AND document_id = %(source_id)s"
        elif key in FILTER_EXACT_KEYS:
            where += f" AND {key} = %({key})s"
        else:
            raise ValueError(f"khóa filter không hỗ trợ: {key}")
        params[key] = value
    return where, params


class Dense:
    name = "dense"
    TABLES = ("lab_chunks", "adv_chunks")  # tên bảng ghép vào SQL: chỉ nhận tên cố định

    def __init__(self, chunks: list[dict], table: str = "lab_chunks", chunking: str = C.CHUNKING):
        if table not in self.TABLES:
            raise ValueError(f"bảng không hỗ trợ: {table}")
        self.by_id = {c["id"]: c for c in chunks}
        self.table, self.chunking = table, chunking

    def search(self, query: str, *, filters: dict | None, top_k: int) -> list[dict]:
        from perry import db, models  # sau lab_config: Perrier đọc biến môi trường lúc import

        where, params = filter_sql(filters)
        try:
            vector = models.embed_query(query)
        except Exception as error:  # Ollama tắt, model chưa pull, timeout…
            raise RetrievalError("embedding", repr(error)) from error
        params |= {"q": str(vector), "chunking": self.chunking, "k": top_k}
        try:
            with db.pool().connection() as conn:
                rows = list(conn.execute(SEARCH_SQL.format(table=self.table, where=where), params))
        except Exception as error:
            raise RetrievalError("vector_store", repr(error)) from error
        missing = [r["chunk_id"] for r in rows if r["chunk_id"] not in self.by_id]
        if missing:
            raise RetrievalError("vector_store", f"chunk trong {self.table} không có trong file chunk: {missing}")
        return [result(self.by_id[r["chunk_id"]], r["score"], rank, self.name) for rank, r in enumerate(rows, 1)]


# --- Hybrid ----------------------------------------------------------------------------


def rrf(rankings: dict[str, list[str]], k: int = RRF_K) -> list[tuple[str, float, dict]]:
    """Reciprocal Rank Fusion: (id, điểm, hạng trong từng ranking), xếp giảm dần theo điểm."""
    scores: dict[str, float] = {}
    ranks: dict[str, dict] = {}
    for name, ids in rankings.items():
        for rank, cid in enumerate(ids, 1):
            scores[cid] = scores.get(cid, 0.0) + 1 / (k + rank)
            ranks.setdefault(cid, {})[name] = rank
    return [(cid, scores[cid], ranks[cid]) for cid in sorted(scores, key=lambda i: (-scores[i], i))]


class Hybrid:
    name = "hybrid"

    def __init__(self, dense, bm25, k: int = RRF_K, depth: int = HYBRID_DEPTH):
        self.parts, self.k, self.depth = {"dense": dense, "bm25": bm25}, k, depth

    def search(self, query: str, *, filters: dict | None, top_k: int) -> list[dict]:
        found = {name: r.search(query, filters=filters, top_k=self.depth) for name, r in self.parts.items()}
        chunks = {c["id"]: c for results in found.values() for c in results}
        fused = rrf({name: [c["id"] for c in results] for name, results in found.items()}, self.k)[:top_k]
        base = lambda c: {k: v for k, v in c.items() if k not in ("score", "rank", "method")}  # noqa: E731
        return [result(base(chunks[cid]), score, rank, self.name, components=parts)
                for rank, (cid, score, parts) in enumerate(fused, 1)]


def build(method: str, chunks: list[dict] | None = None, *, table: str = "lab_chunks",
          chunking: str = C.CHUNKING):
    """`table`/`chunking`: bảng pgvector của corpus (`adv_chunks`/`adv` cho phần nâng cao)."""
    chunks = chunks if chunks is not None else load_chunks()
    if method == "dense":
        return Dense(chunks, table, chunking)
    if method == "bm25":
        return BM25(chunks)
    if method == "hybrid":
        return Hybrid(Dense(chunks, table, chunking), BM25(chunks))
    raise ValueError(f"phương pháp không có: {method}")
