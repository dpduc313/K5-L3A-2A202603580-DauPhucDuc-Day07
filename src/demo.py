"""Demo: một câu có bằng chứng, một câu thiếu bằng chứng (chạy thật) và một lỗi (trace đã lưu).

    python -m src.demo                                   # 3 ví dụ (GUIDE.md mục 5)
    python -m src.demo --ask "Câu hỏi bất kỳ?"           # hỏi tự do bằng cấu hình đã chọn
    python -m src.demo --ask "…" --chapter "Chương II"   # kèm filter do người dùng cho
    python -m src.demo --config dense                    # chạy bằng cấu hình khác

Hai ví dụ đầu chạy agent thật (gpt-5.4-nano, cấu hình đã chọn `searches-2`) trên câu dev, nên
cần database, Ollama và OPENAI_API_KEY như khi chạy thí nghiệm. Chi phí khoảng $0.002. Agent chỉ
nhận câu hỏi và filter (`experiment.agent_inputs`); đáp án chuẩn chỉ in ra SAU khi chạy để đối
chiếu. Ví dụ lỗi đọc từ trace dev đã commit, vì lỗi của model là ngẫu nhiên và chạy lại có thể
không tái hiện; kèm nhãn và lý do của tác giả trong results/labels/answers.csv.

Không ghi gì vào results/.
"""

import argparse
import json
import os

from src import lab_config as C
from src.experiment import CONFIGS, agent_inputs, settings
from src.labels import read_csv

SELECTED = "searches-2"
LIVE_EXAMPLES = ("q10", "u01")  # có bằng chứng; thiếu bằng chứng
ERROR_EXAMPLE = (SELECTED, "q02")  # lỗi 3 trong results/dev_errors.md: bỏ vế cha, mẹ hoặc người giám hộ


def render(t: dict) -> str:
    lines = []
    for i, e in enumerate([e for e in t["events"] if e["event"] == "search"], 1):
        flt = f"  filter={e['filter']}" if e.get("filter") else ""
        lines.append(f"  search {i}: \"{e['query']}\"{flt}")
        lines += [f"    #{r['rank']} {r['id']}  {r['source_id']} tr. {r['page']}  score {r['score']:.4f}"
                  for r in e["results"]]
    lines.append(f"  ngữ cảnh cuối: {', '.join(t['final_context_ids']) or '(trống)'} ({t['final_context_tokens']} token)")
    lines.append(f"  kết quả: {t['status']}  ({t['searches']} lượt tìm, {t['seconds']:.1f} s, ${t['cost_usd']:.5f})")
    lines.append(f"  câu trả lời: {t['answer']}")
    lines.append(f"  citation: {', '.join(t['citations']) or '(không có)'}")
    if t.get("error"):
        lines.append(f"  lỗi: {t['error']}")
    return "\n".join(lines)


def recorded_error() -> dict:
    config, qid = ERROR_EXAMPLE
    traces = json.loads((C.RESULTS / "agent" / config / "dev" / "traces.json").read_text("utf-8"))
    label = next(r for r in read_csv(C.LABELS / "answers.csv") if (r["run"], r["query_id"]) == (f"{config}/dev", qid))
    return {"trace": next(t for t in traces if t["query_id"] == qid), "label": label}


def live(question: dict, config: str) -> dict:
    from src import retrievers as R
    from src.agent import OpenAIController, run_agent, token_counter

    cfg = settings(config)
    inputs = agent_inputs(question)
    controller = OpenAIController(os.getenv("LAB_AGENT_MODEL", "gpt-5.4-nano"), reasoning_effort=cfg["reasoning_effort"])
    return run_agent(inputs["question"], controller, R.build(cfg["method"]), filters=inputs["filters"],
                     max_searches=cfg["max_searches"],
                     top_k=cfg["top_k"], budget=cfg["budget"], count_tokens=token_counter(),
                     extra_rules=cfg["extra_rules"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask", help="câu hỏi tự do")
    parser.add_argument("--chapter", help="filter chapter do người dùng cho, ví dụ 'Chương II'")
    parser.add_argument("--config", default=SELECTED, choices=sorted(CONFIGS))
    args = parser.parse_args()
    print(f"Cấu hình: {args.config} {settings(args.config)}\n")

    if args.ask:
        q = {"question": args.ask, "filter": {"chapter": args.chapter} if args.chapter else None}
        print(f"Câu hỏi: {args.ask}\n{render(live(q, args.config))}")
        return

    questions = {q["id"]: q for q in json.loads(C.QUESTIONS.read_text("utf-8"))}
    titles = {"q10": "1. Câu có bằng chứng (chạy thật)", "u01": "2. Câu thiếu bằng chứng (chạy thật)"}
    for qid in LIVE_EXAMPLES:
        q = questions[qid]
        print(f"=== {titles[qid]}: {qid}\nCâu hỏi: {q['question']}")
        print(render(live(q, args.config)))
        print(f"  [đối chiếu sau khi chạy] {q.get('expected_answer') or q.get('absence_reason')}\n")

    ex = recorded_error()
    q = questions[ex["trace"]["query_id"]]
    print(f"=== 3. Một lỗi (trace đã lưu: results/agent/{ERROR_EXAMPLE[0]}/dev/traces.json, {q['id']})")
    print(f"Câu hỏi: {q['question']}\n{render(ex['trace'])}")
    print(f"  đáp án chuẩn: {q['expected_answer']}")
    print(f"  nhãn grounded của tác giả: {ex['label']['label']}/2 ({ex['label']['reason']})")
    print(f"  lý do chấm: {ex['label']['suggested_reason']}")
    print("  nguyên nhân và thử nghiệm: results/dev_errors.md, lỗi 3")


if __name__ == "__main__":
    main()
