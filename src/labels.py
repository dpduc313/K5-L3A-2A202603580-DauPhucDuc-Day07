"""Bảng nhãn tay cho câu trả lời và citation (results/selection_criteria.md, mục 5).

    python -m src.labels export --split dev [--suggestions <file.json>]
    python -m src.labels summarize --split dev

`export` tạo hoặc cập nhật `results/labels/answers.csv` và `results/labels/citations.csv` từ trace
agent của mọi cấu hình ở split đó (`results/agent/<config>/<split>/traces.json`). Mỗi dòng có:
- cột dữ liệu để đọc đối chiếu (câu hỏi, đáp án chuẩn hoặc lý do thiếu evidence, câu trả lời,
  citation và nguyên văn chunk được trích);
- `suggested_label`, `suggested_reason`: nhãn gợi ý của Mr Duke, chỉ để tham khảo;
- `label`, `reason`: nhãn chính thức do tác giả điền. Chỉ cột này được tính.

Ý nghĩa `label`:
- answers.csv, `kind = grounded` (câu có đáp án): 0 = sai hoặc thiếu evidence, 1 = đúng một
  phần, 2 = đúng và đủ. Câu có đáp án mà agent từ chối phải là 0.
- answers.csv, `kind = abstention` (câu thiếu evidence): 1 = từ chối đúng và không thêm khẳng định
  vô căn cứ, 0 = không.
- citations.csv: 1 = citation có trong ngữ cảnh VÀ chunk hỗ trợ phần câu trả lời gắn với nó, 0 = không.

Chạy lại `export` giữ nguyên nhãn đã điền nếu câu trả lời không đổi; câu trả lời đổi (chạy lại
agent) thì dòng đó về trống để duyệt lại. File ghi bằng UTF-8 có BOM để Excel đọc đúng dấu.

`summarize` báo lỗi nếu còn dòng chưa duyệt, rồi ghi `results/labels/summary_<split>.json`.
Trace có `status: error` không có dòng nhãn; số lỗi báo riêng trong summary của agent.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ANSWER_COLUMNS = ["run", "query_id", "kind", "status", "question", "expected", "answer", "citations",
                  "suggested_label", "suggested_reason", "label", "reason"]
CITATION_COLUMNS = ["run", "query_id", "citation", "in_context", "source_id", "page", "answer", "chunk_text",
                    "suggested_label", "suggested_reason", "label", "reason"]
ANSWER_KEY = ("run", "query_id")
CITATION_KEY = ("run", "query_id", "citation")
REVIEW_FIELDS = ("suggested_label", "suggested_reason", "label", "reason")


class UnreviewedError(ValueError):
    """Còn dòng chưa có nhãn chính thức."""


def blank() -> dict:
    return {k: "" for k in REVIEW_FIELDS}


def answer_rows(questions: dict, traces: list[dict], run: str) -> list[dict]:
    rows = []
    for t in traces:
        if t["status"] == "error":
            continue
        q = questions[t["query_id"]]
        rows.append({"run": run, "query_id": t["query_id"], "kind": "grounded" if q["answerable"] else "abstention",
                     "status": t["status"], "question": q["question"],
                     "expected": q.get("expected_answer") or q.get("absence_reason") or "",
                     "answer": t["answer"], "citations": "; ".join(t.get("citations") or []), **blank()})
    return rows


def citation_rows(traces: list[dict], run: str) -> list[dict]:
    rows = []
    for t in traces:
        if t["status"] != "answered":
            continue
        chunks = {c["id"]: c for c in t["final_context_chunks"]}
        for cid in t["citations"]:
            c = chunks.get(cid, {})
            rows.append({"run": run, "query_id": t["query_id"], "citation": cid, "in_context": str(int(cid in chunks)),
                         "source_id": c.get("source_id", ""), "page": str(c.get("page", "")), "answer": t["answer"],
                         "chunk_text": c.get("text", ""), **blank()})
    return rows


def merge(old: list[dict], new: list[dict], key: tuple[str, ...]) -> list[dict]:
    """Giữ cột gợi ý và nhãn của dòng cũ khi khóa trùng và câu trả lời không đổi."""
    by_key = {tuple(r[k] for k in key): r for r in old}
    merged = []
    for row in new:
        prev = by_key.get(tuple(row[k] for k in key))
        if prev and prev["answer"] == row["answer"]:
            row = {**row, **{k: prev.get(k, "") for k in REVIEW_FIELDS}}
        merged.append(row)
    return merged


def apply_suggestions(rows: list[dict], suggestions: dict, key: tuple[str, ...]) -> None:
    for row in rows:
        s = suggestions.get(tuple(row[k] for k in key))
        if s:
            row["suggested_label"], row["suggested_reason"] = s


def _labels(rows: list[dict], allowed: set[str], what: str) -> list[int]:
    missing = [tuple(r[k] for k in ("run", "query_id")) for r in rows if not r["label"].strip()]
    if missing:
        raise UnreviewedError(f"{what}: {len(missing)} dòng chưa duyệt, ví dụ {missing[:3]}")
    bad = [(r["query_id"], r["label"]) for r in rows if r["label"].strip() not in allowed]
    if bad:
        raise ValueError(f"{what}: nhãn ngoài {sorted(allowed)}: {bad[:3]}")
    return [int(r["label"]) for r in rows]


def summarize(answers: list[dict], citations: list[dict], run: str) -> dict:
    answers = [r for r in answers if r["run"] == run]
    citations = [r for r in citations if r["run"] == run]
    grounded = [r for r in answers if r["kind"] == "grounded"]
    abstention = [r for r in answers if r["kind"] == "abstention"]
    g = _labels(grounded, {"0", "1", "2"}, f"{run} grounded")
    a = _labels(abstention, {"0", "1"}, f"{run} abstention")
    c = _labels(citations, {"0", "1"}, f"{run} citation")
    wrong = [r["query_id"] for r in grounded if r["status"] == "abstain" and r["label"].strip() != "0"]
    if wrong:
        raise ValueError(f"{run}: câu có đáp án bị từ chối phải chấm 0: {wrong}")
    reviewed = answers + citations
    kept = sum(r["label"].strip() == r["suggested_label"].strip() for r in reviewed)
    return {
        "run": run,
        "grounded": {"levels": {str(k): g.count(k) for k in (0, 1, 2)}, "N": len(g),
                     "mean": round(sum(g) / len(g), 4) if g else None},
        "abstention_correct": {"n": sum(a), "N": len(a)},
        "citations_valid": {"n": sum(c), "N": len(c)},
        "review": {"rows": len(reviewed), "kept": kept, "changed": len(reviewed) - kept},
    }


# --- Đọc/ghi -----------------------------------------------------------------------------


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(f)]


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def runs(results: Path, split: str) -> list[tuple[str, Path]]:
    """Các bản chạy agent của split, bỏ `_before_fix` và `-smoke`."""
    return [(f"{p.parent.parent.name}/{split}", p) for p in sorted((results / "agent").glob(f"*/{split}/traces.json"))
            if not p.parent.parent.name.startswith("_")]


def main() -> None:
    from src import lab_config as C

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("export", "summarize"))
    parser.add_argument("--split", required=True, choices=("dev", "test"))
    parser.add_argument("--suggestions", help="JSON: {answers: [[run, qid, label, reason]], citations: [[run, qid, cid, label, reason]]}")
    args = parser.parse_args()
    answers_csv, citations_csv = C.LABELS / "answers.csv", C.LABELS / "citations.csv"
    old_answers, old_citations = read_csv(answers_csv), read_csv(citations_csv)
    found = runs(C.RESULTS, args.split)
    if not found:
        sys.exit(f"Không có trace agent nào cho split {args.split}")

    if args.command == "export":
        questions = {q["id"]: q for q in json.loads(C.QUESTIONS.read_text("utf-8"))}
        new_answers, new_citations = [], []
        for run, path in found:
            traces = json.loads(path.read_text("utf-8"))
            new_answers += answer_rows(questions, traces, run)
            new_citations += citation_rows(traces, run)
        other = lambda rows: [r for r in rows if not r["run"].endswith(f"/{args.split}")]  # noqa: E731
        new_answers = merge(old_answers, new_answers, ANSWER_KEY)
        new_citations = merge(old_citations, new_citations, CITATION_KEY)
        if args.suggestions:
            s = json.loads(Path(args.suggestions).read_text("utf-8"))
            apply_suggestions(new_answers, {(r, q): (lab, why) for r, q, lab, why in s.get("answers", [])}, ANSWER_KEY)
            apply_suggestions(new_citations, {(r, q, c): (lab, why) for r, q, c, lab, why in s.get("citations", [])},
                              CITATION_KEY)
        write_csv(answers_csv, other(old_answers) + new_answers, ANSWER_COLUMNS)
        write_csv(citations_csv, other(old_citations) + new_citations, CITATION_COLUMNS)
        todo = sum(not r["label"] for r in new_answers + new_citations)
        print(f"{len(new_answers)} dòng câu trả lời, {len(new_citations)} dòng citation; {todo} dòng chờ duyệt.")
        print(f"-> {answers_csv.relative_to(C.ROOT)}, {citations_csv.relative_to(C.ROOT)}")
    else:
        summaries = [summarize(old_answers, old_citations, run) for run, _ in found]
        out = C.LABELS / f"summary_{args.split}.json"
        out.write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for s in summaries:
            g = s["grounded"]
            print(f"{s['run']:<20} grounded {g['levels']} mean {g['mean']}/2  abstention "
                  f"{s['abstention_correct']['n']}/{s['abstention_correct']['N']}  citation "
                  f"{s['citations_valid']['n']}/{s['citations_valid']['N']}  review {s['review']}")
        print(f"-> {out.relative_to(C.ROOT)}")


if __name__ == "__main__":
    main()
