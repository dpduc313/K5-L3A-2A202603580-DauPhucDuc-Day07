"""Chunk sách theo mục: text theo mục lục, mỗi bảng và mỗi hình là một chunk riêng.

    python -m src.advanced.chunks

Đọc `data/advanced/parsed/pages.jsonl` (extract) và mô tả hình (describe), ghi `data/advanced/chunks.json`.

- Mục: lấy từ mục lục PDF (outline) kèm toạ độ đích, nên biết mục bắt đầu ở dòng nào của trang.
  Mỗi phần tử thuộc mục cuối cùng bắt đầu trước nó.
- Text: các khối liên tiếp trong cùng một mục, gộp tới `MAX_TOKENS`; không chunk nào vượt
  qua ranh giới mục. Đầu chunk ghi đường dẫn mục để truy vấn theo tên chương/mục tìm được.
- Bảng: Markdown của bảng, cộng đoạn văn ngay trước bảng (thường giới thiệu bảng).
- Hình: caption, mô tả do vision model tạo (đánh dấu rõ là mô tả tự động), và với ảnh không
  caption thì thêm đoạn văn ngay trên ảnh.

Mỗi chunk giữ `page`, `pages`, `locator` (trang + vùng bbox, đơn vị pt, gốc trên-trái) để
người chấm tìm lại đúng chỗ trong bản gốc; chunk hình giữ thêm đường dẫn ảnh crop.
"""

import hashlib
import json

import pymupdf

from src.advanced import config as A

MAX_TOKENS = 350
FRONT_MATTER = "Lời giới thiệu"


def sections() -> list[dict]:
    """Mục lục: (trang, y bắt đầu, cấp, tên) theo thứ tự đọc."""
    doc = pymupdf.open(A.PDF)
    out = []
    for level, title, page, dest in doc.get_toc(simple=False):
        title = " ".join(title.replace("Ph̀n", "Phần").split())
        y = doc[page - 1].rect.height - dest["to"].y if dest.get("to") else 0
        out.append({"page": page, "y": y - 3, "level": level, "title": title})
    return out


def section_at(toc: list[dict], page: int, y: float) -> list[str]:
    """Đường dẫn mục (cấp 1 > 2 > 3) của vị trí (trang, y)."""
    path: dict[int, str] = {}
    for s in toc:
        if (s["page"], s["y"]) > (page, y):
            break
        path = {k: v for k, v in path.items() if k < s["level"]} | {s["level"]: s["title"]}
    return [path[k] for k in sorted(path)] or [FRONT_MATTER]


def locator(page: int, bbox, label: str | None = None) -> str:
    box = ", ".join(f"{v:.0f}" for v in bbox)
    return f"trang {page}" + (f", {label}" if label else "") + f", vùng ({box})"


def chunk(cid: str, kind: str, text: str, page: int, pages: list[int], path: list[str],
          loc: str, **extra) -> dict:
    return {
        "id": cid,
        "source_id": A.DOC_ID,
        "source": A.SOURCE,
        "page": page,
        "locator": loc,
        "text": text,
        "metadata": {
            "kind": kind,
            "pages": pages,
            "chapter": path[1] if len(path) > 1 else path[0],
            "section": path[-1],
            "chapters": path[:2],
            "sections": path,
            "language": "vi",
            "document_type": "book",
            **extra,
        },
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def descriptions() -> dict[str, str]:
    if not A.DESCRIPTIONS.exists():
        return {}
    rows = [json.loads(line) for line in A.DESCRIPTIONS.open(encoding="utf-8")]
    return {r["id"]: r["description"] for r in rows}  # bản sau cùng thắng


def build(pages: list[dict], toc: list[dict], described: dict[str, str], count_tokens) -> list[dict]:
    chunks: list[dict] = []
    text_run: list[tuple[int, dict]] = []
    run_path: list[str] | None = None

    def flush():
        nonlocal text_run
        if not text_run:
            return
        body = "\n".join(b["text"] for _, b in text_run)
        pages_ = sorted({p for p, _ in text_run})
        first_page, first = text_run[0]
        last_page, last = text_run[-1]
        span = f"trang {first_page}" if first_page == last_page else f"trang {first_page}–{last_page}"
        loc = f"{span}, từ vùng ({', '.join(f'{v:.0f}' for v in first['bbox'])}) " \
              f"đến vùng ({', '.join(f'{v:.0f}' for v in last['bbox'])})"
        # ID theo trang bắt đầu (ổn định khi trang khác thay đổi): dlcb-t-p047-1, dlcb-t-p047-2…
        same_page = [c for c in chunks if c["metadata"]["kind"] == "text" and c["page"] == first_page]
        cid = f"{A.DOC_ID}-t-p{first_page:03d}-{len(same_page) + 1}"
        chunks.append(chunk(cid, "text", f"[{' > '.join(run_path)}]\n{body}", first_page, pages_, run_path, loc))
        text_run = []

    for page in pages:
        pno = page["page"]
        items = [(b["bbox"][1], "block", b) for b in page["blocks"]]
        items += [(t["bbox"][1], "table", t) for t in page["tables"]]
        items += [(f["bbox"][1], "figure", f) for f in page["figures"]]
        previous_text = None
        for y, kind, item in sorted(items, key=lambda x: (x[0], x[1])):
            path = section_at(toc, pno, y)
            if kind == "block":
                if path != run_path or (text_run and count_tokens(
                        "\n".join(b["text"] for _, b in text_run) + "\n" + item["text"]) > MAX_TOKENS):
                    flush()
                    run_path = path
                text_run.append((pno, item))
                previous_text = item["text"]
                continue
            header = f"[{' > '.join(path)}]"
            before = f"\nĐoạn văn ngay trước: {previous_text}" if previous_text else ""
            if kind == "table":
                cap = f"\n{item['caption']}" if item["caption"] else ""
                text = f"{header}\nBảng trang {pno}{cap}{before}\n{item['markdown']}"
                chunks.append(chunk(f"{A.DOC_ID}-{item['id']}", "table", text, pno, [pno], path,
                                    locator(pno, item["bbox"], "bảng"), rows=len(item["rows"])))
            else:
                desc = described.get(item["id"])
                title = item["caption"] or item["label"]
                text = f"{header}\n{title}"
                if not item["caption"] and before:
                    text += before
                if desc:
                    text += f"\nMô tả hình (tự động bởi vision model, cần đối chiếu ảnh): {desc}"
                region = item["bbox"] if not item["caption_bbox"] else \
                    list((pymupdf.Rect(item["bbox"]) | pymupdf.Rect(item["caption_bbox"])))
                chunks.append(chunk(f"{A.DOC_ID}-{item['id']}", "figure", text, pno, [pno], path,
                                    locator(pno, region, item["label"]), figure_id=item["id"],
                                    crop=item["crop"], described=bool(desc)))
    flush()
    return chunks


def main() -> None:
    from src.agent import token_counter

    pages = [json.loads(line) for line in A.PAGES_FILE.open(encoding="utf-8")]
    built = build(pages, sections(), descriptions(), token_counter())
    ids = [c["id"] for c in built]
    assert len(ids) == len(set(ids)), "ID chunk bị trùng"
    A.CHUNKS.write_text(json.dumps(built, ensure_ascii=False, indent=1), "utf-8")
    kinds = {k: sum(c["metadata"]["kind"] == k for c in built) for k in ("text", "table", "figure")}
    figures = [c for c in built if c["metadata"]["kind"] == "figure"]
    print(f"{len(built)} chunk: {kinds}; hình có mô tả {sum(c['metadata']['described'] for c in figures)}/{len(figures)}")
    covered = sorted({p for c in built for p in c["metadata"]["pages"]})
    print(f"trang có chunk: {len(covered)}/{A.PAGES}; trang không có: {sorted(set(range(1, A.PAGES + 1)) - set(covered))}")
    longest = max(built, key=lambda c: len(c["text"]))
    print(f"chunk dài nhất {longest['id']}: {len(longest['text'])} ký tự")


if __name__ == "__main__":
    main()
