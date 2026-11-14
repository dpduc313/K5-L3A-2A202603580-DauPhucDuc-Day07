"""Dữ liệu benchmark Day 7: chuyển chunk Day 6 sang schema Day 7 và kiểm tra bộ câu hỏi.

    python -m src.benchmark chunks   # data/parsed/chunks-heading.jsonl -> data/chunks.json
    python -m src.benchmark verify   # kiểm tra data/questions.json với chunk và trang

Thay cho starter/convert_day6.py (đánh rơi metadata `chapter`/`section` vì Day 6 để chúng ở
cấp ngoài) và verify_benchmark.py của Day 6 (benchmark A/B/C). Chỉ dùng thư viện chuẩn và
`lab_config.normalize`, không import Perrier, nên chạy được không cần database.

`verify` kiểm tra:
- schema và số câu tối thiểu theo split (BENCHMARK.md: dev 15+2, test 5+2);
- mỗi gold nằm trọn trong ít nhất một chunk đúng nguồn và trang (sau `normalize`);
- câu có filter: chunk chứa gold phải thỏa filter, nếu không filter sẽ loại mất evidence;
- câu thiếu evidence: chạy lại regex trong `absence_check` trên toàn bộ trang và so với số
  kết quả đã ghi lúc tác giả duyệt.
"""

import json
import re
import sys
import unicodedata
from collections import Counter

from src import lab_config as C

CHUNK_METADATA = ("chapter", "section", "chapters", "sections", "language", "document_type",
                  "chunking", "start", "chars", "tokens", "text_sha256")
# Khóa filter cho phép và cách khớp: chapter/section khớp khi chunk TRẢI QUA heading đó
# (danh sách `chapters`/`sections`), giống Day 6 (src/evaluate.py `follows`).
FILTER_LIST_KEYS = {"chapter": "chapters", "section": "sections"}
FILTER_EXACT_KEYS = {"language", "document_type", "source_id"}
MINIMUM = {("dev", True): 15, ("dev", False): 2, ("test", True): 5, ("test", False): 2}


def read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def to_day7_chunk(row: dict) -> dict:
    """Một dòng chunk Day 6 -> chunk theo data/README.md (id, text, source_id, source, page, metadata)."""
    return {"id": row["chunk_id"], "text": row["text"], "source_id": row["document_id"],
            "source": row["source"], "page": row["page"],
            "metadata": {key: row[key] for key in CHUNK_METADATA}}


def contains_evidence(chunk: dict, gold: dict) -> bool:
    """Định nghĩa hit dùng chung cho mọi phương pháp: đúng nguồn, đúng trang, evidence nằm
    trọn trong text chunk sau khi cả hai được `normalize`."""
    return (chunk["source_id"] == gold["source_id"] and chunk["page"] == gold["page"]
            and C.normalize(gold["evidence"]) in C.normalize(chunk["text"]))


def satisfies(chunk: dict, flt: dict | None) -> bool:
    if not flt:
        return True
    for key, value in flt.items():
        if key in FILTER_LIST_KEYS:
            if value not in chunk["metadata"][FILTER_LIST_KEYS[key]]:
                return False
        elif key == "source_id":
            if chunk["source_id"] != value:
                return False
        elif key in FILTER_EXACT_KEYS:
            if chunk["metadata"].get(key) != value:
                return False
        else:
            raise ValueError(f"khóa filter không hỗ trợ: {key}")
    return True


def count_matches(pages: list[dict], source_id: str, pattern: str) -> tuple[int, list[int]]:
    """Số lần regex khớp trên mọi trang của một tài liệu (NFC + casefold, không qua retrieval)."""
    hits = [p["page"] for p in pages if p["document_id"] == source_id
            for _ in re.finditer(pattern, unicodedata.normalize("NFC", p["text"]).casefold())]
    return len(hits), sorted(set(hits))


def verify(questions: list[dict], chunks: list[dict], pages: list[dict]) -> list[str]:
    """Danh sách lỗi; rỗng nghĩa là bộ câu hỏi hợp lệ."""
    errors = []
    ids = [q.get("id") for q in questions]
    errors += [f"ID trùng: {i}" for i, n in Counter(ids).items() if n > 1]
    count = Counter((q.get("split"), q.get("answerable")) for q in questions)
    errors += [f"{split} {'có' if ans else 'thiếu'} evidence: {count[(split, ans)]} < {n}"
               for (split, ans), n in MINIMUM.items() if count[(split, ans)] < n]
    for q in questions:
        qid = q.get("id")
        if q.get("split") not in ("dev", "test") or not str(q.get("question", "")).strip():
            errors.append(f"{qid}: split hoặc question không hợp lệ")
            continue
        if q.get("answerable") is True:
            if not str(q.get("expected_answer", "")).strip() or not q.get("gold"):
                errors.append(f"{qid}: thiếu expected_answer hoặc gold")
                continue
            for g in q["gold"]:
                found = [c for c in chunks if contains_evidence(c, g)]
                if not found:
                    errors.append(f"{qid}: gold {g['source_id']} tr.{g['page']} không nằm trọn trong chunk nào")
                elif not any(satisfies(c, q.get("filter")) for c in found):
                    errors.append(f"{qid}: chunk chứa gold không thỏa filter {q.get('filter')}")
        elif q.get("answerable") is False:
            if q.get("expected_behavior") != "search_and_abstain" or not q.get("absence_reason"):
                errors.append(f"{qid}: thiếu expected_behavior hoặc absence_reason")
            check = q.get("absence_check") or {}
            for r in check.get("results", []):
                n, at = count_matches(pages, check["source_id"], r["pattern"])
                if (n, at) != (r["hits"], r["pages"]):
                    errors.append(f"{qid}: regex {r['pattern']!r} giờ khớp {n} lần ở trang {at}, "
                                  f"đã ghi {r['hits']} lần ở trang {r['pages']}")
            if not check.get("results"):
                errors.append(f"{qid}: thiếu absence_check")
        else:
            errors.append(f"{qid}: answerable phải là true hoặc false")
    return errors


def write_chunks() -> None:
    rows = read_jsonl(C.PARSED / f"chunks-{C.CHUNKING}.jsonl")
    chunks = [to_day7_chunk(r) for r in rows]
    if len({c["id"] for c in chunks}) != len(chunks):
        sys.exit("ID chunk trùng")
    C.CHUNKS.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{C.CHUNKS.relative_to(C.ROOT)}: {len(chunks)} chunk ({C.CHUNKING})")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "chunks":
        write_chunks()
    elif command == "verify":
        questions = json.loads(C.QUESTIONS.read_text("utf-8"))
        chunks = json.loads(C.CHUNKS.read_text("utf-8"))
        pages = read_jsonl(C.PARSED / "pages.jsonl")
        errors = verify(questions, chunks, pages)
        count = Counter((q["split"], q["answerable"]) for q in questions)
        print(f"{len(questions)} câu: dev {count[('dev', True)]}+{count[('dev', False)]}, "
              f"test {count[('test', True)]}+{count[('test', False)]}; {len(chunks)} chunk")
        for e in errors:
            print("✗", e)
        print("Hợp lệ." if not errors else f"{len(errors)} lỗi.")
        sys.exit(1 if errors else 0)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
