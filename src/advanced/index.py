"""Nạp `data/advanced/chunks.json` vào bảng pgvector `adv_chunks` (riêng, không đụng `lab_chunks`).

    python -m src.advanced.index

Cùng cách làm với `src/index.py` của phần cơ bản: embed bằng `embeddinggemma-2` qua Perrier,
chunk có `text_sha256` không đổi thì bỏ qua, chunk đổi thì embed lại, chunk không còn thì xóa.
Mỗi lần chạy ghi một dòng vào `results/advanced/index_log.jsonl` (kèm sha256 của file chunk).
"""

import datetime as dt
import hashlib
import json
import time

from src import lab_config as C  # noqa: F401  (biến môi trường, Perrier)
from src.advanced import config as A
from perry import db, models  # noqa: E402

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS {A.TABLE} (
    chunk_id      text PRIMARY KEY,
    chunking      text NOT NULL,
    document_id   text NOT NULL,
    page          int  NOT NULL,
    kind          text NOT NULL,
    locator       text NOT NULL,
    chapter       text NOT NULL,
    section       text NOT NULL,
    chapters      text[] NOT NULL,
    sections      text[] NOT NULL,
    language      text NOT NULL,
    document_type text NOT NULL,
    text          text NOT NULL,
    text_sha256   text NOT NULL,
    embedding     vector({models.EMBEDDING_DIMENSIONS}) NOT NULL,
    embedding_model text NOT NULL,
    indexed_at    timestamptz NOT NULL DEFAULT now()
);
"""

UPSERT = f"""
INSERT INTO {A.TABLE} (chunk_id, chunking, document_id, page, kind, locator, chapter, section,
    chapters, sections, language, document_type, text, text_sha256, embedding, embedding_model)
VALUES (%(chunk_id)s, %(chunking)s, %(document_id)s, %(page)s, %(kind)s, %(locator)s, %(chapter)s,
    %(section)s, %(chapters)s, %(sections)s, %(language)s, %(document_type)s, %(text)s,
    %(text_sha256)s, %(embedding)s::vector, %(model)s)
ON CONFLICT (chunk_id) DO UPDATE SET
    page = EXCLUDED.page, kind = EXCLUDED.kind, locator = EXCLUDED.locator,
    chapter = EXCLUDED.chapter, section = EXCLUDED.section, chapters = EXCLUDED.chapters,
    sections = EXCLUDED.sections, text = EXCLUDED.text, text_sha256 = EXCLUDED.text_sha256,
    embedding = EXCLUDED.embedding, embedding_model = EXCLUDED.embedding_model, indexed_at = now()
"""

BATCH = 32


def row(c: dict) -> dict:
    m = c["metadata"]
    return {"chunk_id": c["id"], "chunking": A.CHUNKING, "document_id": c["source_id"], "page": c["page"],
            "kind": m["kind"], "locator": c["locator"], "chapter": m["chapter"], "section": m["section"],
            "chapters": m["chapters"], "sections": m["sections"], "language": m["language"],
            "document_type": m["document_type"], "text": c["text"], "text_sha256": c["text_sha256"]}


def main() -> None:
    started = time.monotonic()
    raw = A.CHUNKS.read_bytes()
    chunks = json.loads(raw)
    with db.pool().connection() as conn:
        conn.execute(SCHEMA, prepare=False)
        stored = {r["chunk_id"]: (r["text_sha256"], r["embedding_model"])
                  for r in conn.execute(f"SELECT chunk_id, text_sha256, embedding_model FROM {A.TABLE}")}
    model = models.embedding_model()
    todo = [c for c in chunks if stored.get(c["id"]) != (c["text_sha256"], model)]
    gone = sorted(set(stored) - {c["id"] for c in chunks})
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        vectors = models.embed_documents([c["text"] for c in batch])
        with db.pool().connection() as conn, conn.transaction():
            for c, vector in zip(batch, vectors, strict=True):
                conn.execute(UPSERT, {**row(c), "embedding": str(vector), "model": model})
        print(f"embedded {min(start + BATCH, len(todo))}/{len(todo)}", flush=True)
    with db.pool().connection() as conn:
        if gone:
            conn.execute(f"DELETE FROM {A.TABLE} WHERE chunk_id = ANY(%s)", (gone,))
        total = conn.execute(f"SELECT count(*) AS n FROM {A.TABLE}").fetchone()["n"]
    log = {"at": dt.datetime.now().isoformat(timespec="seconds"),
           "chunks_sha256": hashlib.sha256(raw).hexdigest()[:12], "chunks": len(chunks),
           "embedded": len(todo), "unchanged": len(chunks) - len(todo), "deleted": len(gone),
           "stored": total, "embedding_model": model, "seconds": round(time.monotonic() - started, 1)}
    if total != len(chunks):
        raise SystemExit(f"Bảng có {total} dòng, file chunk có {len(chunks)}: {log}")
    A.RESULTS.mkdir(parents=True, exist_ok=True)
    with (A.RESULTS / "index_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")
    print(log)


if __name__ == "__main__":
    main()
