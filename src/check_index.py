"""Đối chiếu index Lab07 với vector store Day 6 (chunking heading) và ghi minh chứng.

    python -m src.check_index --reference postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab

So từng chunk theo `chunk_id`: `text_sha256`, `embedding_model`, và cosine giữa hai vector
embedding. Kết quả ghi vào results/index_check.json (commit làm minh chứng "kết nối vector
store Day 6", GUIDE.md:5). Chỉ cần chạy khi database Day 6 còn; khi đó không còn thì file
kết quả đã commit là bằng chứng.
"""

import argparse
import datetime as dt
import json

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from src import lab_config as C

QUERY = ("SELECT chunk_id, text_sha256, embedding_model, embedding FROM lab_chunks "
         "WHERE chunking = %s ORDER BY chunk_id")


def load(url: str) -> dict[str, dict]:
    with psycopg.connect(url) as conn:
        register_vector(conn)
        return {r[0]: {"sha": r[1], "model": r[2], "vec": r[3].to_numpy().astype(float)}
                for r in conn.execute(QUERY, (C.CHUNKING,))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, help="DATABASE_URL của vector store Day 6")
    ref_url = parser.parse_args().reference
    lab, ref = load(C.DATABASE_URL), load(ref_url)
    shared = sorted(set(lab) & set(ref))
    cos = [float(lab[i]["vec"] @ ref[i]["vec"] / (np.linalg.norm(lab[i]["vec"]) * np.linalg.norm(ref[i]["vec"])))
           for i in shared]
    report = {
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "chunking": C.CHUNKING,
        "lab07": {"database": C.DATABASE_URL.split("@")[-1], "chunks": len(lab)},
        "day6": {"database": ref_url.split("@")[-1], "chunks": len(ref)},
        "only_in_lab07": sorted(set(lab) - set(ref)),
        "only_in_day6": sorted(set(ref) - set(lab)),
        "text_sha256_mismatch": [i for i in shared if lab[i]["sha"] != ref[i]["sha"]],
        "embedding_models": sorted({lab[i]["model"] for i in lab} | {ref[i]["model"] for i in ref}),
        "embedding_model_mismatch": [i for i in shared if lab[i]["model"] != ref[i]["model"]],
        "embedding_cosine": {"min": min(cos), "mean": float(np.mean(cos))} if cos else None,
        "dimensions": sorted({len(v["vec"]) for v in [*lab.values(), *ref.values()]}),
    }
    report["identical"] = (not report["only_in_lab07"] and not report["only_in_day6"]
                           and not report["text_sha256_mismatch"] and not report["embedding_model_mismatch"])
    C.RESULTS.mkdir(exist_ok=True)
    out = C.RESULTS / "index_check.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
