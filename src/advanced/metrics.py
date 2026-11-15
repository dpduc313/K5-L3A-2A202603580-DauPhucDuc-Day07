"""Metric tự động của phần nâng cao (không thay nhãn tay đạt/không đạt).

Evidence của mỗi câu là danh sách chunk (`evidence[].chunk_id`). Chấm sau khi chạy, gold không
đi vào agent.

- Retrieval (query gốc, top-5): `any@5` có ít nhất một chunk evidence, `all@5` có đủ mọi chunk
  evidence (quan trọng với multi-hop).
- Agent: `context_all` ngữ cảnh cuối có đủ chunk evidence; `cites_all` câu trả lời trích đủ mọi
  chunk evidence; `viewed_gold` (câu hình/biểu đồ) đã xem ảnh của hình evidence;
  `auto_pass` = câu có đáp án: trả lời và trích đủ evidence; câu thiếu evidence: từ chối.
  `auto_pass` chỉ là chỉ báo: nó không kiểm tra nội dung câu trả lời đúng hay sai.
- Lỗi hệ thống tính không đạt, nằm trong mẫu số, báo riêng.
"""

from collections import Counter, defaultdict

from src.metrics import percentile, ratio


def gold_ids(question: dict) -> set[str]:
    return {e["chunk_id"] for e in question.get("evidence", [])}


def score_retrieval(question: dict, ranked: list[dict], k: int = 5) -> dict:
    gold = gold_ids(question)
    found = {r["id"] for r in ranked[:k]}
    return {"query_id": question["id"], "group": question["group"],
            "any": bool(gold & found) if gold else None, "all": gold <= found if gold else None}


def score_agent(question: dict, trace: dict) -> dict:
    gold = gold_ids(question)
    answerable = question["group"] != "unanswerable"
    status = trace["status"]
    figures = {e["chunk_id"] for e in question.get("evidence", []) if e["kind"] == "figure"}
    row = {"query_id": question["id"], "group": question["group"], "status": status,
           "error": status == "error",
           "context_all": gold <= set(trace["final_context_ids"]) if answerable else None,
           "cites_all": (status == "answered" and gold <= set(trace["citations"])) if answerable else None,
           "viewed_gold": bool(figures & set(trace.get("viewed_figures", []))) if figures else None,
           "views": len(trace.get("viewed_figures", [])),
           "searches": trace["searches"], "seconds": trace["seconds"], "cost_usd": trace["cost_usd"]}
    row["auto_pass"] = row["cites_all"] if answerable else status == "abstain"
    return row


def summarize_retrieval(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["any"] is not None]
    return {"any@5": ratio(sum(r["any"] for r in scored), len(scored)),
            "all@5": ratio(sum(r["all"] for r in scored), len(scored)),
            "by_group": {g: {"any@5": ratio(sum(r["any"] for r in rs), len(rs)),
                             "all@5": ratio(sum(r["all"] for r in rs), len(rs))}
                         for g, rs in _groups([r for r in scored]).items()}}


def summarize_agent(rows: list[dict]) -> dict:
    answerable = [r for r in rows if r["group"] != "unanswerable"]
    visual = [r for r in rows if r["viewed_gold"] is not None]
    seconds = [r["seconds"] for r in rows]
    return {
        "questions": len(rows),
        "auto_pass": ratio(sum(bool(r["auto_pass"]) for r in rows), len(rows)),
        "auto_pass_by_group": {g: ratio(sum(bool(r["auto_pass"]) for r in rs), len(rs))
                               for g, rs in _groups(rows).items()},
        "context_all": ratio(sum(bool(r["context_all"]) for r in answerable), len(answerable)),
        "cites_all": ratio(sum(bool(r["cites_all"]) for r in answerable), len(answerable)),
        "viewed_gold_figure": ratio(sum(bool(r["viewed_gold"]) for r in visual), len(visual)),
        "status": dict(Counter(r["status"] for r in rows)),
        "errors": [r["query_id"] for r in rows if r["error"]],
        "searches": dict(sorted(Counter(r["searches"] for r in rows).items())),
        "views": dict(sorted(Counter(r["views"] for r in rows).items())),
        "seconds_median": percentile(seconds, 0.5),
        "seconds_p95": percentile(seconds, 0.95),
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
    }


def _groups(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["group"]].append(r)
    return dict(sorted(out.items()))
