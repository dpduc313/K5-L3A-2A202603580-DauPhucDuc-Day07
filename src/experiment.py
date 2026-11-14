"""Chạy thí nghiệm: retrieval không qua agent, hoặc agent đầy đủ, trên một split.

    python -m src.experiment retrieval --method dense --split dev
    python -m src.experiment agent --config dense --split dev
    python -m src.experiment agent --config dense --split dev --ids q01,u01   # chạy thử, ghi vào <split>-smoke

Kết quả:
- results/retrieval/<method>/<split>/{traces,summary}.json: query gốc, top-5 kèm score và
  hạng, cờ hit (tính SAU khi chạy, bằng gold); Hit@1, Evidence Hit@3. Câu có filter được chạy
  thêm một lần không filter, báo riêng.
- results/agent/<config>/<split>/{traces,summary}.json: toàn bộ trace của `run_agent` và
  metric tự động (src/metrics.py).

Gold chỉ dùng để chấm sau khi chạy: agent và retriever chỉ nhận `agent_inputs(question)`.
Split `test` bị chặn cho đến khi results/selection.md đã được commit (chốt cấu hình trước).
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

from src import lab_config as C
from src import metrics as M
from src import retrievers as R

# Giá trị mặc định của agent (results/selection_criteria.md, mục 2).
AGENT_DEFAULTS = {"max_searches": 4, "top_k": 5, "budget": 2000, "reasoning_effort": "none"}
CONFIGS = {
    "dense": {"method": "dense", "role": "baseline"},
    "bm25": {"method": "bm25", "role": "phương pháp 2"},
    "hybrid": {"method": "hybrid", "role": "phương pháp 3"},
}
RETRIEVAL_TOP_K = 5


def agent_inputs(question: dict) -> dict:
    """Những gì agent được thấy từ một câu benchmark: câu hỏi và filter người dùng cho."""
    return {"question": question["question"], "filters": question.get("filter")}


def git_state() -> dict:
    run = lambda *a: subprocess.run(["git", *a], cwd=C.ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    return {"commit": run("rev-parse", "--short", "HEAD"), "dirty": bool(run("status", "--porcelain", "--", "src"))}


def guard_test_split() -> None:
    path = C.RESULTS / "selection.md"
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], cwd=C.ROOT,
                             capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], cwd=C.ROOT).returncode == 0
    if not (path.exists() and tracked and clean):
        sys.exit("Từ chối chạy test: results/selection.md chưa được commit (phải chốt cấu hình trên dev trước).")


def load_questions(split: str, ids: list[str] | None) -> list[dict]:
    questions = [q for q in json.loads(C.QUESTIONS.read_text("utf-8")) if q["split"] == split]
    if ids:
        unknown = set(ids) - {q["id"] for q in questions}
        if unknown:
            sys.exit(f"ID không có trong split {split}: {sorted(unknown)}")
        questions = [q for q in questions if q["id"] in ids]
    return questions


def write(out_dir, traces, summary) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in (("traces.json", traces), ("summary.json", summary)):
        (out_dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"-> {out_dir.relative_to(C.ROOT)}")


def run_retrieval(method: str, split: str, ids: list[str] | None) -> None:
    questions = load_questions(split, ids)
    retriever = R.build(method)
    traces, rows, rows_nofilter = [], [], []
    for q in questions:
        variants = [("filter", q.get("filter"))] + ([("no_filter", None)] if q.get("filter") else [])
        for variant, flt in variants:
            t0 = time.perf_counter()
            ranked = retriever.search(agent_inputs(q)["question"], filters=flt, top_k=RETRIEVAL_TOP_K)
            seconds = time.perf_counter() - t0
            row = M.score_retrieval(q, ranked)
            (rows if variant == "filter" else rows_nofilter).append(row)
            traces.append({"query_id": q["id"], "variant": variant, "query": q["question"], "filter": flt,
                           "seconds": seconds, **{k: row[k] for k in ("hit1", "hit3", "first_hit_rank")},
                           "results": [{**{k: r[k] for k in ("id", "source_id", "page", "score", "rank")},
                                        **({"components": r["components"]} if "components" in r else {}),
                                        "chapters": r["metadata"].get("chapters"),
                                        "hit": M.has_evidence(q, [r]) if q["answerable"] else None}
                                       for r in ranked]})
    filtered_ids = {q["id"] for q in questions if q.get("filter")}
    summary = {"method": method, "split": split, "query": "câu hỏi gốc", "top_k_exported": RETRIEVAL_TOP_K,
               "cutoff": 3, "run_at": dt.datetime.now().isoformat(timespec="seconds"), **git_state(),
               **M.summarize_retrieval(rows),
               "filter_questions": {"ids": sorted(filtered_ids),
                                    "with_filter": M.summarize_retrieval([r for r in rows if r["query_id"] in filtered_ids]),
                                    "without_filter": M.summarize_retrieval(rows_nofilter)},
               "seconds_median": M.percentile([t["seconds"] for t in traces if t["variant"] == "filter"], 0.5),
               "cost_usd": 0.0}
    out = C.RESULTS / "retrieval" / method / (split if not ids else f"{split}-smoke")
    write(out, traces, summary)


def run_agent_config(config: str, split: str, ids: list[str] | None, model: str) -> None:
    from src.agent import OpenAIController, run_agent, token_counter

    questions = load_questions(split, ids)
    settings = {**AGENT_DEFAULTS, **CONFIGS[config]}
    retriever = R.build(settings["method"])
    controller = OpenAIController(model, reasoning_effort=settings["reasoning_effort"])
    count_tokens = token_counter()
    traces = []
    for q in questions:
        inputs = agent_inputs(q)
        out = run_agent(inputs["question"], controller, retriever, filters=inputs["filters"],
                        max_searches=settings["max_searches"], top_k=settings["top_k"],
                        budget=settings["budget"], count_tokens=count_tokens)
        traces.append({"query_id": q["id"], "question": q["question"], "answerable": q["answerable"], **out})
        mark = {"answered": "✓", "abstain": "–", "error": "✗"}[out["status"]]
        print(f"{mark} {q['id']} {out['status']:<8} searches={out['searches']} "
              f"ctx={out['final_context_tokens']}tok {out['seconds']:.1f}s ${out['cost_usd']:.5f}", flush=True)
    summary = {"config": config, "split": split, "model": model, "settings": settings,
               "run_at": dt.datetime.now().isoformat(timespec="seconds"), **git_state(),
               **M.summarize_agent(questions, traces)}
    out = C.RESULTS / "agent" / config / (split if not ids else f"{split}-smoke")
    write(out, traces, summary)


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
            p.add_argument("--model", default=os.getenv("LAB_AGENT_MODEL", "gpt-5.4-nano"))
    args = parser.parse_args()
    if args.split == "test":
        guard_test_split()
    ids = args.ids.split(",") if args.ids else None
    if args.command == "retrieval":
        run_retrieval(args.method, args.split, ids)
    else:
        run_agent_config(args.config, args.split, ids, args.model)


if __name__ == "__main__":
    main()
