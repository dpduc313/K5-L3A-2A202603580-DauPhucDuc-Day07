"""Trang HTML để tác giả duyệt benchmark nâng cao (thay cho CSV mở bằng Excel).

    python -m src.advanced.review

Ghi `results/advanced/review/benchmark.html` và ảnh vùng evidence trong `review/evidence/`.
Mỗi câu hiện: câu hỏi, đáp án, phép tính; với từng evidence: ảnh crop vùng đó từ PDF gốc (bảng,
đoạn text) hoặc ảnh crop hình, chữ đã trích (đoạn quote được tô), mô tả tự động của hình, và link mở
PDF đúng trang. Câu thiếu evidence hiện regex đã chạy và số lần khớp.

Tác giả chọn "OK" hoặc "Sửa" + ghi chú cho từng câu; trang tự lưu nháp trong trình duyệt và có nút lưu
file `results/advanced/benchmark_review.json` (kèm sha256 của questions.json để phát hiện duyệt trên
bản cũ). Chạy lại lệnh này thì quyết định đã lưu trong file đó được nạp sẵn vào trang.
"""

import hashlib
import html
import json
import re

import pymupdf

from src import lab_config as C
from src.advanced import config as A

OUT = A.RESULTS / "review"
EVIDENCE = OUT / "evidence"
DECISIONS = A.RESULTS / "benchmark_review.json"
TEMPLATE = C.ROOT / "src" / "advanced" / "review_template.html"
DPI = 110


def rel(path) -> str:
    """Đường dẫn tương đối từ thư mục trang HTML."""
    return "../" * len(OUT.relative_to(C.ROOT).parts) + path.relative_to(C.ROOT).as_posix()


def highlight(text: str, quote: str | None) -> str:
    """HTML của `text`, tô `quote` (khớp bỏ qua khác biệt khoảng trắng)."""
    if not quote:
        return html.escape(text)
    pattern = r"\s*".join(re.escape(t) for t in quote.split())
    m = re.search(pattern, text)
    if not m:
        return html.escape(text)
    return (html.escape(text[: m.start()]) + "<mark>" + html.escape(m.group(0)) + "</mark>"
            + html.escape(text[m.end():]))


def quote_region(page: dict, quote: str) -> list[float] | None:
    """Vùng của khối text trên trang chứa quote (sau normalize)."""
    q = C.normalize(quote)
    for b in page["blocks"]:
        if q in C.normalize(b["text"]):
            return b["bbox"]
    return None


def render(doc, page_no: int, bbox, name: str) -> str:
    page = doc[page_no - 1]
    clip = (pymupdf.Rect(bbox) + (-12, -8, 12, 8)) & page.rect if bbox else page.rect
    path = EVIDENCE / f"{name}.jpg"
    page.get_pixmap(clip=clip, dpi=DPI if bbox else 60).save(path, jpg_quality=80)
    return rel(path)


def build() -> dict:
    questions = json.loads(A.QUESTIONS.read_text("utf-8"))
    chunks = {c["id"]: c for c in json.loads(A.CHUNKS.read_text("utf-8"))}
    pages = {p["page"]: p for p in map(json.loads, A.PAGES_FILE.open(encoding="utf-8"))}
    descriptions = {}
    if A.DESCRIPTIONS.exists():
        for line in A.DESCRIPTIONS.open(encoding="utf-8"):
            r = json.loads(line)
            descriptions[r["id"]] = r["description"]
    doc = pymupdf.open(A.PDF)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for old in EVIDENCE.glob("*.jpg"):
        old.unlink()
    pdf = rel(A.PDF)
    items = []
    for q in questions:
        evidence = []
        for n, e in enumerate(q.get("evidence", []), 1):
            c = chunks[e["chunk_id"]]
            item = {"page": e["page"], "kind": e["kind"], "locator": e["locator"], "chunk_id": e["chunk_id"],
                    "quote": e.get("quote"), "chunk_locator": c["locator"], "pdf": f"{pdf}#page={e['page']}",
                    "text_html": highlight(c["text"], e.get("quote") if e["kind"] != "figure" else None)}
            if e["kind"] == "figure":
                item["image"] = rel(C.ROOT / c["metadata"]["crop"])
                item["description"] = descriptions.get(c["metadata"]["figure_id"])
                item["image_note"] = "Ảnh crop hình (đúng ảnh agent xem bằng view_figure)"
            elif e["kind"] == "table":
                table = next(t for t in pages[e["page"]]["tables"] if c["id"].endswith(t["id"]))
                item["image"] = render(doc, e["page"], table["bbox"], f"{q['id']}-{n}")
                item["image_note"] = "Vùng bảng trong PDF gốc"
            else:
                region = quote_region(pages[e["page"]], e["quote"])
                item["image"] = render(doc, e["page"], region, f"{q['id']}-{n}")
                item["image_note"] = ("Đoạn chứa quote trong PDF gốc" if region
                                      else "Không định vị được đoạn, hiện cả trang")
            evidence.append(item)
        items.append({k: q.get(k) for k in ("id", "split", "group", "tags", "question", "expected_answer",
                                             "calculation", "reason", "absence_reason", "absence_check")}
                     | {"evidence": evidence, "pdf": pdf})
    sha = hashlib.sha256(A.QUESTIONS.read_bytes()).hexdigest()
    saved = json.loads(DECISIONS.read_text("utf-8")) if DECISIONS.exists() else None
    return {"questions_sha256": sha, "questions": items, "saved": saved}


def main() -> None:
    data = build()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.read_text("utf-8").replace("/*DATA*/null", payload)
    out = OUT / "benchmark.html"
    out.write_text(page, "utf-8")
    saved = data["saved"]
    note = ""
    if saved:
        note = f"; nạp {len(saved.get('decisions', {}))} quyết định đã lưu"
        if saved.get("questions_sha256") != data["questions_sha256"]:
            note += " (duyệt trên bản questions.json cũ: trang sẽ đánh dấu)"
    print(f"{len(data['questions'])} câu -> {out.relative_to(C.ROOT)}{note}")


if __name__ == "__main__":
    main()
