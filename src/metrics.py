"""Metric tự động (không cần nhãn tay) theo results/selection_criteria.md, mục 3.

Retrieval (không qua agent, query gốc): Hit@1 và Evidence Hit@3 trên câu có đáp án.
Agent: Context Evidence Rate, tool use, phân bố số lượt tìm, từ chối (theo status), lỗi, thời
gian và chi phí. Câu lỗi nằm trong mẫu số và tính là không đạt; số lỗi báo riêng.
Grounded answer và citation hợp lệ cần nhãn tay, tính ở bước tổng hợp nhãn.
"""

from collections import Counter

from src.benchmark import contains_evidence


def has_evidence(question: dict, chunks: list[dict]) -> bool:
    return any(contains_evidence(c, g) for c in chunks for g in question["gold"])


def ratio(n: int, total: int) -> dict:
    return {"n": n, "N": total, "rate": round(n / total, 4) if total else None}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    i = (len(s) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def score_retrieval(question: dict, ranked: list[dict]) -> dict:
    """Hit của một câu với danh sách đã xếp hạng (chỉ xét top-3). Câu thiếu evidence: None."""
    if not question.get("answerable"):
        return {"query_id": question["id"], "answerable": False, "hit1": None, "hit3": None, "first_hit_rank": None}
    marks = [has_evidence(question, [c]) for c in ranked[:3]]
    return {"query_id": question["id"], "answerable": True, "hit1": bool(marks and marks[0]), "hit3": any(marks),
            "first_hit_rank": next((i for i, m in enumerate(marks, 1) if m), None)}


def summarize_retrieval(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["answerable"]]
    return {"hit1": ratio(sum(r["hit1"] for r in scored), len(scored)),
            "hit3": ratio(sum(r["hit3"] for r in scored), len(scored))}


def summarize_agent(questions: list[dict], traces: list[dict]) -> dict:
    by_id = {t["query_id"]: t for t in traces}
    missing = [q["id"] for q in questions if q["id"] not in by_id]
    if missing:
        raise ValueError(f"thiếu trace: {missing}")
    answerable = [q for q in questions if q["answerable"]]
    unanswerable = [q for q in questions if not q["answerable"]]
    ok = [by_id[q["id"]] for q in questions if by_id[q["id"]]["status"] != "error"]
    status = lambda q: by_id[q["id"]]["status"]  # noqa: E731
    seconds = [by_id[q["id"]]["seconds"] for q in questions]
    costs = [by_id[q["id"]]["cost_usd"] for q in questions]
    return {
        "questions": len(questions),
        "status": dict(Counter(status(q) for q in questions)),
        "errors": sum(status(q) == "error" for q in questions),
        "context_evidence": ratio(sum(status(q) != "error" and has_evidence(q, by_id[q["id"]]["final_context_chunks"])
                                      for q in answerable), len(answerable)),
        "tool_use": ratio(sum(t["searches"] > 0 for t in ok), len(ok)),
        "searches_distribution": {str(k): v for k, v in sorted(Counter(t["searches"] for t in ok).items())},
        "abstained_unanswerable": ratio(sum(status(q) == "abstain" for q in unanswerable), len(unanswerable)),
        "false_abstention": ratio(sum(status(q) == "abstain" for q in answerable), len(answerable)),
        "answered_with_citations": ratio(sum(bool(by_id[q["id"]].get("citations")) for q in questions
                                             if status(q) == "answered"),
                                         sum(status(q) == "answered" for q in questions)),
        "seconds": {"median": percentile(seconds, 0.5), "p90": percentile(seconds, 0.9)},
        "cost_usd": {"total": round(sum(costs), 6), "per_question": round(sum(costs) / len(costs), 6) if costs else None},
        "tokens": {"input": sum(by_id[q["id"]].get("input_tokens", 0) for q in questions),
                   "output": sum(by_id[q["id"]].get("output_tokens", 0) for q in questions)},
    }
