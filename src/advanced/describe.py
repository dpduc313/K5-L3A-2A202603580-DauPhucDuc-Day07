"""Mô tả mỗi hình một lần bằng vision model, để hình tìm được bằng truy vấn chữ.

    python -m src.advanced.describe --limit 2      # thử, xem chi phí mỗi hình
    python -m src.advanced.describe                # toàn bộ, dừng khi chạm --max-usd

Mô tả chỉ phục vụ retrieval. Khi trả lời, agent xem chính ảnh crop bằng tool `view_figure`,
nên câu trả lời về hình dựa trên ảnh gốc, không chỉ dựa trên mô tả do model tạo.

Kết quả ghi nối tiếp vào `data/advanced/parsed/figure_descriptions.jsonl`, khóa theo ID hình
và sha256 của ảnh crop: chạy lại chỉ mô tả hình mới hoặc hình có crop đổi. Hình ở chương 1
(ảnh chụp màn hình cài đặt) không mô tả, chỉ index caption.
"""

import argparse
import hashlib
import json
import time

from src import lab_config as C  # noqa: F401  (biến môi trường, Perrier)
from src.advanced import config as A

MODEL = "gpt-5.4-mini"
PROMPT = """Đây là một hình trong sách "Deep Learning cơ bản" (tiếng Việt).
{where}

Mô tả hình để người khác tìm được nó bằng truy vấn chữ. Viết tiếng Việt, tối đa 150 từ:
- Loại hình (biểu đồ đường, biểu đồ cột, sơ đồ mạng neural, sơ đồ khối, ảnh minh họa, bảng dạng ảnh…).
- Hình thể hiện điều gì.
- Với biểu đồ: tên trục, đơn vị, khoảng giá trị, chú giải, xu hướng và các giá trị đọc được rõ.
- Chép nguyên văn các chữ, số, nhãn đọc được trong hình.
Chỉ mô tả những gì nhìn thấy trong hình. Không suy đoán, không thêm kiến thức ngoài hình."""


def todo_figures() -> list[dict]:
    out = []
    for line in A.PAGES_FILE.open(encoding="utf-8"):
        page = json.loads(line)
        if page["page"] in A.SCREENSHOT_PAGES:
            continue
        for f in page["figures"]:
            if f.get("crop"):
                out.append({**f, "page": page["page"]})
    return out


def done() -> dict[str, dict]:
    if not A.DESCRIPTIONS.exists():
        return {}
    rows = [json.loads(line) for line in A.DESCRIPTIONS.open(encoding="utf-8")]
    return {(r["id"], r["crop_sha256"]): r for r in rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="chỉ mô tả N hình (thử)")
    parser.add_argument("--max-usd", type=float, default=0.45, help="dừng khi tổng chi phí lần chạy chạm mức này")
    args = parser.parse_args()

    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI
    from perry import images, usage

    chat = ChatOpenAI(model=MODEL, reasoning_effort="none", timeout=120, max_retries=3)
    cached = done()
    figures = todo_figures()
    pending = []
    for f in figures:
        data = (C.ROOT / f["crop"]).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if (f["id"], sha) not in cached:
            pending.append((f, data, sha))
    print(f"{len(figures)} hình cần mô tả, {len(figures) - len(pending)} đã có, còn {len(pending)}")
    spent = 0.0
    with A.DESCRIPTIONS.open("a", encoding="utf-8") as out:
        for n, (f, data, sha) in enumerate(pending[: args.limit] if args.limit else pending, 1):
            if spent >= args.max_usd:
                print(f"Dừng: đã chi ${spent:.4f} ≥ --max-usd {args.max_usd}")
                break
            where = f"Trang {f['page']}. " + (f"Caption: {f['caption']}" if f["caption"] else "Hình không có caption.")
            message = HumanMessage([{"type": "text", "text": PROMPT.format(where=where)},
                                    images.image_block(data, "image/jpeg")])
            t0 = time.perf_counter()
            reply = chat.invoke([message])
            meta = reply.usage_metadata or {}
            model = (reply.response_metadata or {}).get("model_name", MODEL)
            cost = usage.cost(model, meta.get("input_tokens", 0), meta.get("output_tokens", 0))
            spent += cost
            row = {"id": f["id"], "page": f["page"], "crop_sha256": sha, "model": model,
                   "description": reply.text.strip(), "input_tokens": meta.get("input_tokens", 0),
                   "output_tokens": meta.get("output_tokens", 0), "cost_usd": cost,
                   "seconds": round(time.perf_counter() - t0, 2)}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{n}/{len(pending)}] {f['id']} p{f['page']} in={row['input_tokens']} "
                  f"out={row['output_tokens']} ${cost:.5f} (tổng ${spent:.4f})", flush=True)


if __name__ == "__main__":
    main()
