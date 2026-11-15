"""Benchmark phần nâng cao: schema và kiểm tra `data/advanced/questions.json`.

    python -m src.advanced.benchmark

Mỗi câu:
- `id`, `split` (dev/test), `group` (table, figure, chart, multihop, text, unanswerable),
  `tags` (nhóm phụ), `question`, `reason`.
- Câu có đáp án: `expected_answer`, `calculation` (nếu có phép tính), `evidence`: danh sách
  {page, kind (text/table/figure), chunk_id, locator, quote}. `locator` mô tả chỗ trong bản
  gốc (đoạn, hàng/cột bảng, vùng hình). Với text và bảng, `quote` phải nằm trọn trong chunk
  (sau `normalize`); với hình, `quote` là điều nhìn thấy trong ảnh, tác giả đối chiếu bằng mắt.
- Câu thiếu bằng chứng: `expected_behavior = "search_and_abstain"`, `absence_reason`, và
  `absence_check`: các regex chạy trên toàn bộ text, bảng và caption của sách, kèm số lần
  khớp và trang đã ghi lúc duyệt (để phát hiện nếu chunk/parse đổi).

Kiểm tra số câu tối thiểu theo ADVANCED.md: test ≥ 6 bảng, 5 ảnh/sơ đồ, 5 biểu đồ,
4 multi-hop, 4 text, 6 thiếu evidence; dev ≥ 15 có đáp án + 3 thiếu evidence.
"""

import json
import re
import sys
import unicodedata
from collections import Counter

from src import lab_config as C
from src.advanced import config as A

GROUPS = ("table", "figure", "chart", "multihop", "text", "unanswerable")
TEST_MINIMUM = {"table": 6, "figure": 5, "chart": 5, "multihop": 4, "text": 4, "unanswerable": 6}
DEV_MINIMUM = {"answerable": 15, "unanswerable": 3}


def page_texts() -> dict[int, str]:
    """Text kiểm tra được của từng trang: khối text, bảng và caption (không gồm mô tả do model tạo)."""
    out = {}
    for line in A.PAGES_FILE.open(encoding="utf-8"):
        p = json.loads(line)
        parts = [b["text"] for b in p["blocks"]] + [t["markdown"] for t in p["tables"]]
        parts += [f["caption"] for f in p["figures"] if f["caption"]]
        out[p["page"]] = unicodedata.normalize("NFC", "\n".join(parts)).casefold()
    return out


def count_matches(pages: dict[int, str], pattern: str) -> tuple[int, list[int]]:
    hits = [n for n, text in pages.items() for _ in re.finditer(pattern, text)]
    return len(hits), sorted(set(hits))


def verify(questions: list[dict], chunks: list[dict], pages: dict[int, str]) -> tuple[list[str], list[str]]:
    """(lỗi, cảnh báo)."""
    errors, warnings = [], []
    by_id = {c["id"]: c for c in chunks}
    ids = [q.get("id") for q in questions]
    errors += [f"ID trùng: {i}" for i, n in Counter(ids).items() if n > 1]
    test = Counter(q.get("group") for q in questions if q.get("split") == "test")
    errors += [f"test nhóm {g}: {test[g]} < {n}" for g, n in TEST_MINIMUM.items() if test[g] < n]
    dev = Counter("unanswerable" if q.get("group") == "unanswerable" else "answerable"
                  for q in questions if q.get("split") == "dev")
    errors += [f"dev {k}: {dev[k]} < {n}" for k, n in DEV_MINIMUM.items() if dev[k] < n]
    evidence_sets: dict[str, list[tuple[str, frozenset]]] = {"dev": [], "test": []}
    for q in questions:
        qid = q.get("id")
        if q.get("split") not in ("dev", "test") or q.get("group") not in GROUPS:
            errors.append(f"{qid}: split hoặc group không hợp lệ")
            continue
        if not str(q.get("question", "")).strip() or not str(q.get("reason", "")).strip():
            errors.append(f"{qid}: thiếu question hoặc reason")
        if q["group"] == "unanswerable":
            if q.get("expected_behavior") != "search_and_abstain" or not q.get("absence_reason"):
                errors.append(f"{qid}: thiếu expected_behavior hoặc absence_reason")
            results = (q.get("absence_check") or {}).get("results", [])
            if not results:
                errors.append(f"{qid}: thiếu absence_check")
            for r in results:
                n, at = count_matches(pages, r["pattern"])
                if (n, at) != (r["hits"], r["pages"]):
                    errors.append(f"{qid}: regex {r['pattern']!r} khớp {n} lần ở trang {at}, "
                                  f"đã ghi {r['hits']} lần ở trang {r['pages']}")
            continue
        if not str(q.get("expected_answer", "")).strip() or not q.get("evidence"):
            errors.append(f"{qid}: thiếu expected_answer hoặc evidence")
            continue
        for e in q["evidence"]:
            c = by_id.get(e.get("chunk_id"))
            if c is None:
                errors.append(f"{qid}: chunk {e.get('chunk_id')} không có")
                continue
            if e.get("page") not in c["metadata"]["pages"] or not e.get("locator"):
                errors.append(f"{qid}: evidence {c['id']} sai trang hoặc thiếu locator")
            if e.get("kind") != c["metadata"]["kind"]:
                errors.append(f"{qid}: evidence {c['id']} kind {e.get('kind')} khác chunk {c['metadata']['kind']}")
            if e.get("kind") in ("text", "table"):
                if not e.get("quote") or C.normalize(e["quote"]) not in C.normalize(c["text"]):
                    errors.append(f"{qid}: quote không nằm trọn trong {c['id']}: {e.get('quote')!r}")
        chunk_ids = frozenset(e.get("chunk_id") for e in q["evidence"])
        if q["group"] == "multihop" and len(chunk_ids) < 2:
            errors.append(f"{qid}: multi-hop cần evidence từ ít nhất 2 chunk")
        kinds = {by_id[i]["metadata"]["kind"] for i in chunk_ids if i in by_id}
        need = {"table": "table", "figure": "figure", "chart": "figure"}.get(q["group"])
        if need and need not in kinds:
            errors.append(f"{qid}: nhóm {q['group']} nhưng không có evidence loại {need}")
        evidence_sets[q["split"]].append((qid, chunk_ids))
    for tid, tset in evidence_sets["test"]:
        for did, dset in evidence_sets["dev"]:
            if tset == dset:
                errors.append(f"{tid} (test) và {did} (dev) cùng một bộ evidence {sorted(tset)}")
            elif tset & dset:
                warnings.append(f"{tid} (test) và {did} (dev) chung evidence {sorted(tset & dset)}")
    return errors, warnings


def main() -> None:
    questions = json.loads(A.QUESTIONS.read_text("utf-8"))
    chunks = json.loads(A.CHUNKS.read_text("utf-8"))
    errors, warnings = verify(questions, chunks, page_texts())
    for split in ("dev", "test"):
        count = Counter(q["group"] for q in questions if q["split"] == split)
        print(f"{split}: {sum(count.values())} câu {dict(sorted(count.items()))}")
    for w in warnings:
        print("!", w)
    for e in errors:
        print("✗", e)
    print("Hợp lệ." if not errors else f"{len(errors)} lỗi.")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
