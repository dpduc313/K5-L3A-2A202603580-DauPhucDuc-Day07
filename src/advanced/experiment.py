"""Chạy thí nghiệm phần nâng cao trên `adv_chunks` và `data/advanced/questions.json`.

    python -m src.advanced.experiment retrieval --method dense --split dev
    python -m src.advanced.experiment agent --config dense --split dev
    python -m src.advanced.experiment agent --config dense --split dev --ids adv-d01   # ghi vào <split>-smoke
    python -m src.advanced.experiment ask "Câu hỏi tự do" --config dense             # không thuộc benchmark

Kết quả ở `results/advanced/{retrieval,agent}/<tên>/<split>/{traces,summary}.json`.
Agent chỉ nhận câu hỏi; evidence, đáp án và lý do chỉ dùng để chấm sau khi chạy.
Split `test` bị chặn cho đến khi `results/advanced/selection.md` đã được commit.
"""

import argparse
import datetime as dt
import functools
import json
import os
import sys
import time

from src import lab_config as C
from src import retrievers as R
from src.advanced import config as A
from src.advanced import metrics as M
from src.experiment import git_state, write

TOP_K = 5
# Quy tắc riêng của phần nâng cao, dùng cho MỌI cấu hình (không phải biến thí nghiệm).
ADV_RULES = (
    "Ngữ cảnh có ba loại chunk: text, bảng (Markdown) và hình. Chunk hình gồm caption và một mô tả do "
    "vision model tạo tự động, có thể sai. Câu hỏi về nội dung hình, biểu đồ, sơ đồ: gọi `view_figure` với "
    "ID chunk hình để xem ảnh gốc trước khi trả lời; ảnh và mô tả khác nhau thì theo ảnh.",
    "Khác với quy tắc 4: được làm phép tính đơn giản (cộng, trừ, nhân, chia, so sánh) trên các số có trong "
    "ngữ cảnh hoặc đọc được từ ảnh khi câu hỏi yêu cầu, và ghi rõ phép tính. Vẫn không dùng số không có trong tài liệu.",
    "Câu hỏi cần thông tin từ nhiều chỗ (nhiều trang, bảng, hình): tìm đủ từng phần và trích citation cho "
    "từng phần; thông tin đọc từ hình thì trích chunk hình, đọc từ bảng thì trích chunk bảng.",
)
AGENT_DEFAULTS = {"max_searches": 4, "top_k": TOP_K, "budget": 2000, "max_views": 2, "view": True,
                  "reasoning_effort": "none", "model": "gpt-5.4-nano", "extra_rules": ADV_RULES}
# Cấu hình có `base` chỉ đổi đúng một yếu tố so với `base` (results/advanced/selection_criteria.md).
CONFIGS = {
    "dense": {"method": "dense", "role": "baseline"},
    "bm25": {"base": "dense", "method": "bm25", "role": "phương pháp 2"},
    "hybrid": {"base": "dense", "method": "hybrid", "role": "phương pháp 3"},
    "no-view": {"base": "dense", "view": False, "role": "đối chứng: không xem ảnh"},
}


def settings(config: str) -> dict:
    cfg = CONFIGS[config]
    base = settings(cfg["base"]) if "base" in cfg else AGENT_DEFAULTS
    return {**base, **cfg}


def load_chunks() -> list[dict]:
    return json.loads(A.CHUNKS.read_text("utf-8"))


def retriever(method: str):
    return R.build(method, load_chunks(), table=A.TABLE, chunking=A.CHUNKING)


@functools.lru_cache(maxsize=None)
def _image(path: str) -> dict:
    from perry import images

    return images.image_block((C.ROOT / path).read_bytes(), "image/jpeg")


def figure_viewer(chunk: dict) -> dict | None:
    """Ảnh crop của chunk hình (content block cho model), None nếu chunk không phải hình."""
    crop = chunk.get("metadata", {}).get("crop")
    return _image(crop) if crop else None


def guard_test_split() -> None:
    import subprocess

    path = A.RESULTS / "selection.md"
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], cwd=C.ROOT,
                             capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], cwd=C.ROOT).returncode == 0
    if not (path.exists() and tracked and clean):
        sys.exit("Từ chối chạy test: results/advanced/selection.md chưa được commit.")


def load_questions(split: str, ids: list[str] | None) -> list[dict]:
    questions = [q for q in json.loads(A.QUESTIONS.read_text("utf-8")) if q["split"] == split]
    if ids:
        unknown = set(ids) - {q["id"] for q in questions}
        if unknown:
            sys.exit(f"ID không có trong split {split}: {sorted(unknown)}")
        questions = [q for q in questions if q["id"] in ids]
    return questions


def run_retrieval(method: str, split: str, ids: list[str] | None) -> None:
    r = retriever(method)
    traces, rows = [], []
    for q in load_questions(split, ids):
        t0 = time.perf_counter()
        ranked = r.search(q["question"], filters=None, top_k=TOP_K)
        row = M.score_retrieval(q, ranked)
        rows.append(row)
        gold = M.gold_ids(q)
        traces.append({"query_id": q["id"], "group": q["group"], "query": q["question"],
                       "seconds": time.perf_counter() - t0, "any": row["any"], "all": row["all"],
                       "results": [{"id": c["id"], "page": c["page"], "kind": c["metadata"]["kind"],
                                    "score": c["score"], "rank": c["rank"], "gold": c["id"] in gold}
                                   for c in ranked]})
    summary = {"method": method, "split": split, "top_k": TOP_K,
               "run_at": dt.datetime.now().isoformat(timespec="seconds"), **git_state(),
               **M.summarize_retrieval(rows), "cost_usd": 0.0}
    write(A.RESULTS / "retrieval" / method / (split if not ids else f"{split}-smoke"), traces, summary)


def run_one(question: str, cfg: dict, controller, r, count_tokens) -> dict:
    from src.agent import run_agent

    return run_agent(question, controller, r, filters=None, max_searches=cfg["max_searches"], top_k=cfg["top_k"],
                     budget=cfg["budget"], count_tokens=count_tokens, extra_rules=cfg["extra_rules"],
                     viewer=figure_viewer if cfg["view"] else None, max_views=cfg["max_views"])


def run_agent_config(config: str, split: str, ids: list[str] | None) -> None:
    from src.agent import OpenAIController, token_counter

    cfg = settings(config)
    controller = OpenAIController(cfg["model"], reasoning_effort=cfg["reasoning_effort"])
    r, count_tokens = retriever(cfg["method"]), token_counter()
    questions = load_questions(split, ids)
    traces, rows = [], []
    for q in questions:
        out = run_one(q["question"], cfg, controller, r, count_tokens)
        traces.append({"query_id": q["id"], "group": q["group"], "question": q["question"], **out})
        row = M.score_agent(q, out)
        rows.append(row)
        mark = {"answered": "✓", "abstain": "–", "error": "✗"}[out["status"]]
        print(f"{mark} {q['id']} {q['group']:<12} {out['status']:<8} auto_pass={row['auto_pass']} "
              f"s={out['searches']} v={row['views']} {out['seconds']:.1f}s ${out['cost_usd']:.5f}", flush=True)
    summary = {"config": config, "split": split, "settings": {k: v for k, v in cfg.items() if k != "extra_rules"},
               "extra_rules": list(cfg["extra_rules"]), "run_at": dt.datetime.now().isoformat(timespec="seconds"),
               **git_state(), **M.summarize_agent(rows), "rows": rows}
    write(A.RESULTS / "agent" / config / (split if not ids else f"{split}-smoke"), traces, summary)


def ask(question: str, config: str) -> None:
    from src.agent import OpenAIController, token_counter

    cfg = settings(config)
    out = run_one(question, cfg, OpenAIController(cfg["model"], reasoning_effort=cfg["reasoning_effort"]),
                  retriever(cfg["method"]), token_counter())
    for e in out["events"]:
        if e["event"] == "model_call":
            print(f"· model → {e['tool']} {json.dumps(e['args'], ensure_ascii=False)[:160]} "
                  f"(in={e['input_tokens']} out={e['output_tokens']})")
        elif e["event"] == "search":
            print(f"  search: {[(r['id'], round(r['score'], 3)) for r in e['results']]}")
        elif e["event"] in ("view_figure", "invalid_view", "invalid_citations", "error"):
            print(f"  {e['event']}: {json.dumps({k: v for k, v in e.items() if k != 'event'}, ensure_ascii=False)[:200]}")
    print(f"\n[{out['status']}] {out['answer']}\ncitations={out['citations']} viewed={out['viewed_figures']} "
          f"{out['seconds']:.1f}s ${out['cost_usd']:.5f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("retrieval", "agent"):
        p = sub.add_parser(name)
        p.add_argument("--split", required=True, choices=("dev", "test"))
        p.add_argument("--ids", help="chỉ chạy các ID này (phân tách bằng dấu phẩy); ghi vào <split>-smoke")
        if name == "retrieval":
            p.add_argument("--method", required=True, choices=("dense", "bm25", "hybrid"))
        else:
            p.add_argument("--config", required=True, choices=sorted(CONFIGS))
    p = sub.add_parser("ask")
    p.add_argument("question")
    p.add_argument("--config", default="dense", choices=sorted(CONFIGS))
    args = parser.parse_args()
    if args.command == "ask":
        ask(args.question, args.config)
        return
    if args.split == "test":
        guard_test_split()
    ids = args.ids.split(",") if args.ids else None
    if args.command == "retrieval":
        run_retrieval(args.method, args.split, ids)
    else:
        run_agent_config(args.config, args.split, ids)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
