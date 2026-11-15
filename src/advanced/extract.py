"""Đọc PDF sách thành khối text, hình (kèm ảnh crop) và bảng, giữ trang và vùng (bbox, đơn vị pt).

    python -m src.advanced.extract

PDF là bản LaTeX có lớp text, nhưng lớp text mất dấu cách sau nhiều chữ có dấu ("Đồthịquan").
Vì vậy không dùng `get_text()` mặc định mà ghép lại từng dòng từ vị trí glyph (`rawdict`):
khoảng hở giữa hai glyph lớn hơn `SPACE_RATIO` × chiều cao glyph là một dấu cách. Không cần OCR.

- Hình: mỗi caption "Hình N.M: …" nhận các ảnh raster nằm ngay phía trên nó (cùng trang, giao
  nhau theo chiều ngang). Caption không có ảnh thì lấy cụm nét vẽ vector phía trên. Vùng hình
  cộng caption được render thành PNG (`CROP_DPI`) trong `data/advanced/figures/`.
- Bảng: `find_tables` của PyMuPDF (bảng có kẻ ô); chữ trong từng ô cũng ghép lại theo glyph.
- Khối text: mọi khối còn lại, trừ dòng đầu trang, caption, và khối nằm trong vùng hình/bảng.

Ghi `data/advanced/parsed/pages.jsonl` và báo cáo kiểm tra `results/advanced/extraction_report.json`
(token dính dấu thanh, ảnh không có caption, caption không có ảnh, bảng tìm được).
"""

import json
import re
import unicodedata

import pymupdf

from src.advanced import config as A

CAPTION = re.compile(r"^Hình (\d+\.\d+):")
TABLE_CAPTION = re.compile(r"^Bảng (\d+\.\d+):")
TONES = set("\u0300\u0301\u0303\u0309\u0323")
MIN_IMAGE = 20  # pt; nhỏ hơn là ký hiệu trang trí
MAX_CELL = 40  # ký tự; ô dài hơn là đoạn văn, không phải bảng


def chars_text(chars: list[dict], ratio: float = A.SPACE_RATIO) -> str:
    """Ghép một dãy glyph cùng dòng thành chữ, chèn dấu cách theo khoảng hở."""
    text, prev = "", None
    for c in chars:
        if prev is not None and c["c"] != " " and prev["c"] != " ":
            gap = c["bbox"][0] - prev["bbox"][2]
            height = (c["bbox"][3] - c["bbox"][1]) or 1
            if gap > ratio * height:
                text += " "
        text += c["c"]
        prev = c
    return unicodedata.normalize("NFC", " ".join(text.split()))


def line_chars(line: dict) -> list[dict]:
    return [c for span in line["spans"] for c in span["chars"]]


def glued_tokens(text: str) -> list[str]:
    """Token có từ hai dấu thanh trở lên: một âm tiết tiếng Việt chỉ có một, nên đây là hai
    âm tiết bị dính (dấu hiệu ghép dấu cách thất bại)."""
    return [t for t in re.findall(r"[^\W\d_]+", text)
            if sum(ch in TONES for ch in unicodedata.normalize("NFD", t)) >= 2]


def rect(bbox) -> list[float]:
    return [round(v, 1) for v in bbox]


def union(boxes) -> pymupdf.Rect:
    out = pymupdf.Rect(boxes[0])
    for b in boxes[1:]:
        out |= pymupdf.Rect(b)
    return out


def inside(inner, outer, slack: float = 2) -> bool:
    """Tâm của `inner` nằm trong `outer` (nới `slack` pt)."""
    r = pymupdf.Rect(inner)
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    o = pymupdf.Rect(outer)
    return o.x0 - slack <= cx <= o.x1 + slack and o.y0 - slack <= cy <= o.y1 + slack


def overlaps_x(a, b) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > 0


def text_blocks(raw: dict) -> list[dict]:
    blocks = []
    for b in raw["blocks"]:
        lines = [l for l in b.get("lines", []) if line_chars(l)]
        texts = [chars_text(line_chars(l)) for l in lines]
        if not any(texts):
            continue
        spans = [s for l in lines for s in l["spans"] if s["chars"]]
        fonts = {s["font"] for s in spans}
        blocks.append({
            "bbox": rect(b["bbox"]),
            "text": "\n".join(t for t in texts if t),
            "size": round(max(s["size"] for s in spans), 1),
            "bold": all(("Bo" in f or "Demi" in f) for f in fonts),
            "lines": [{"bbox": rect(l["bbox"]), "chars": line_chars(l)} for l in lines],
        })
    return blocks


def text_in(blocks: list[dict], region) -> str:
    """Chữ của các glyph có tâm trong `region`, theo từng dòng (dùng cho ô bảng)."""
    out = []
    for b in blocks:
        for line in b["lines"]:
            chars = [c for c in line["chars"] if inside(c["bbox"], region, slack=0.5)]
            if chars:
                out.append(chars_text(chars))
    return " ".join(t for t in out if t)


def markdown(rows: list[list[str]]) -> str:
    cell = lambda v: (v or "").replace("|", "\\|").replace("\n", " ")  # noqa: E731
    lines = ["| " + " | ".join(cell(v) for v in rows[0]) + " |", "|" + "---|" * len(rows[0])]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def find_figures(page: pymupdf.Page, blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    captions = [b for b in blocks if CAPTION.match(b["text"])]
    images = [i for i in page.get_image_info()
              if i["bbox"][2] - i["bbox"][0] >= MIN_IMAGE and i["bbox"][3] - i["bbox"][1] >= MIN_IMAGE]
    owned: dict[int, list] = {id(c): [] for c in captions}
    orphans = []
    body = [b for b in blocks if not CAPTION.match(b["text"])]

    def text_between(img, cap) -> bool:
        """Có đoạn văn nằm giữa ảnh và caption: ảnh không thuộc caption đó (trang 131)."""
        return any(overlaps_x(b["bbox"], img) and b["bbox"][1] >= img[3] - 2 and b["bbox"][3] <= cap[1] + 2
                   for b in body)

    for img in images:
        below = [c for c in captions if c["bbox"][1] >= img["bbox"][3] - 3 and overlaps_x(c["bbox"], img["bbox"])
                 and not text_between(img["bbox"], c["bbox"])]
        if below:
            owner = min(below, key=lambda c: c["bbox"][1] - img["bbox"][3])
            owned[id(owner)].append(img["bbox"])
        else:
            orphans.append({"page": page.number + 1, "bbox": rect(img["bbox"])})
    # Ảnh không có caption vẫn có thể chứa thông tin (vd. đồ thị tính toán trang 72): thành hình
    # riêng `img-pNNN-k`. Bỏ bìa, banner đầu chương (rộng hết trang, sát mép trên) và ảnh chụp
    # màn hình cài đặt ở chương 1.
    pno = page.number + 1
    uncaptioned = []
    for o in orphans:
        b = o["bbox"]
        if pno == 1 or (b[2] - b[0] > page.rect.width - 2 and b[1] < 1) or pno in A.SCREENSHOT_PAGES:
            o["skipped"] = "bìa" if pno == 1 else "ảnh chụp màn hình cài đặt" if pno in A.SCREENSHOT_PAGES else "banner chương"
            continue
        uncaptioned.append(o)
    drawings = [r for r in page.cluster_drawings() if r.width >= MIN_IMAGE and r.height >= MIN_IMAGE]
    figures = []
    for c in captions:
        boxes, kind = owned[id(c)], "image"
        if not boxes:
            above = [r for r in drawings if r.y1 <= c["bbox"][1] + 3]
            if above:
                boxes, kind = [max(above, key=lambda r: r.y1)], "drawing"
        number = CAPTION.match(c["text"]).group(1)
        figures.append({
            "id": f"fig-{number}",
            "label": f"Hình {number}",
            "caption": " ".join(c["text"].split()),
            "bbox": rect(union(boxes)) if boxes else None,
            "caption_bbox": c["bbox"],
            "kind": kind if boxes else "missing",
            "images": len(boxes),
        })
    for k, o in enumerate(sorted(uncaptioned, key=lambda o: o["bbox"][1]), 1):
        o["figure"] = f"img-p{pno:03d}-{k}"
        figures.append({"id": o["figure"], "label": f"Ảnh không caption trang {pno}", "caption": None,
                        "bbox": o["bbox"], "caption_bbox": None, "kind": "image", "images": 1})
    return figures, orphans


def find_tables(page: pymupdf.Page, blocks: list[dict]) -> list[dict]:
    tables = []
    for n, t in enumerate(page.find_tables().tables, 1):
        if t.row_count < 2 or t.col_count < 2:
            continue
        rows = [[text_in(blocks, cell) if cell else "" for cell in row.cells] for row in t.rows]
        if any(len(v) > MAX_CELL for r in rows for v in r):
            continue  # câu văn bị tô màu nền (trang 4), không phải bảng; giữ lại làm text
        near = lambda b: abs(b["bbox"][1] - t.bbox[3]) < 30 or abs(b["bbox"][3] - t.bbox[1]) < 30  # noqa: E731
        caption = next((b["text"] for b in blocks if TABLE_CAPTION.match(b["text"]) and near(b)), None)
        tables.append({"id": f"tab-p{page.number + 1:03d}-{n}", "bbox": rect(t.bbox),
                       "caption": caption, "rows": rows, "markdown": markdown(rows)})
    return tables


def crop(page: pymupdf.Page, figure: dict) -> str | None:
    if figure["bbox"] is None:
        return None
    clip = pymupdf.Rect(figure["bbox"])
    if figure["caption_bbox"]:
        clip |= pymupdf.Rect(figure["caption_bbox"])
    clip = (clip + (-4, -4, 4, 4)) & page.rect
    path = A.FIGURES / f"{figure['id']}.jpg"
    page.get_pixmap(clip=clip, dpi=A.CROP_DPI).save(path, jpg_quality=A.CROP_QUALITY)
    return path.relative_to(A.C.ROOT).as_posix()


def main() -> None:
    doc = pymupdf.open(A.PDF)
    if len(doc) != A.PAGES:
        raise SystemExit(f"PDF có {len(doc)} trang, cần {A.PAGES}")
    A.PARSED.mkdir(parents=True, exist_ok=True)
    A.FIGURES.mkdir(parents=True, exist_ok=True)
    A.RESULTS.mkdir(parents=True, exist_ok=True)
    report = {"pages": len(doc), "space_ratio": A.SPACE_RATIO, "glued_tokens": [], "orphan_images": [],
              "figures_without_region": [], "duplicate_figure_ids": [], "tables": [], "empty_pages": [],
              "blocks_inside_regions": []}
    seen: set[str] = set()
    counts = {"blocks": 0, "figures": 0, "tables": 0}
    with A.PAGES_FILE.open("w", encoding="utf-8") as out:
        for page in doc:
            pno = page.number + 1
            raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
            blocks = [b for b in text_blocks(raw) if b["bbox"][3] > A.HEADER_BOTTOM]
            figures, orphans = find_figures(page, blocks)
            tables = find_tables(page, blocks)
            regions = [f["bbox"] for f in figures if f["bbox"]] + [t["bbox"] for t in tables]
            body = [b for b in blocks if not CAPTION.match(b["text"])
                    and not any(inside(b["bbox"], r) for r in regions)]
            # Khối text bị bỏ vì nằm trong vùng hình/bảng: chữ trong hình vẽ vector hoặc chữ trong
            # ô bảng thì đúng; đoạn văn thật thì là lỗi gán vùng. Ghi lại để kiểm tra bằng mắt.
            report["blocks_inside_regions"] += [
                {"page": pno, "text": b["text"][:80]} for b in blocks
                if not CAPTION.match(b["text"]) and b not in body]
            for f in figures:
                if f["id"] in seen:
                    report["duplicate_figure_ids"].append(f["id"])
                    f["id"] += f"-p{pno}"
                seen.add(f["id"])
                f["crop"] = crop(page, f)
                if f["bbox"] is None:
                    report["figures_without_region"].append({"page": pno, "id": f["id"], "caption": f["caption"]})
            for b in body:
                report["glued_tokens"] += [{"page": pno, "token": t} for t in glued_tokens(b["text"])]
            if not body and not figures and not tables:
                report["empty_pages"].append(pno)
            report["orphan_images"] += orphans
            report["tables"] += [{"page": pno, "id": t["id"], "size": [len(t["rows"]), len(t["rows"][0])],
                                  "caption": t["caption"], "header": t["rows"][0]} for t in tables]
            counts["blocks"] += len(body)
            counts["figures"] += len(figures)
            counts["tables"] += len(tables)
            record = {"page": pno,
                      "blocks": [{k: b[k] for k in ("bbox", "text", "size", "bold")} for b in body],
                      "figures": figures, "tables": tables}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    report["counts"] = counts
    (A.RESULTS / "extraction_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({**counts, **{k: len(v) for k, v in report.items() if isinstance(v, list)}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
