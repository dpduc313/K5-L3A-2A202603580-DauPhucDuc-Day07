# Code

Mọi lệnh chạy từ gốc repo bằng `uv run python -m src.<module>`; xem [README](../README.md#chạy-lại).

| Module | Vai trò |
|---|---|
| `lab_config.py` | Đường dẫn, biến môi trường, nạp Perrier từ `src/perrier`. Phải import trước mọi `import perry`. |
| `retrievers.py` | Dense, BM25, hybrid RRF; cùng một dạng kết quả, filter áp trước khi xếp hạng. |
| `agent.py` | Vòng lặp agent, tool `search`/`answer`/`abstain`, đóng gói ngữ cảnh, kiểm tra citation, gọi OpenAI. |
| `experiment.py` | Cấu hình thí nghiệm và runner; chặn split test khi `results/selection.md` chưa commit. |
| `metrics.py` | Metric tự động. |
| `labels.py` | Bảng nhãn tay và tổng hợp. |
| `demo.py` | Lệnh demo. |
| `benchmark.py` | Schema dữ liệu Day 7, kiểm tra bộ câu hỏi. |
| `parse_docs.py`, `index.py`, `check_index.py` | Đọc, chunk, nạp pgvector, đối chiếu với Day 6. |
| `check_setup.py` | Kiểm tra môi trường. |
| `perry_app.py`, `perrier_retrieval.py` | Chạy giao diện chat của Perrier trên DB của lab. Đây là phần demo riêng, không phải agent Day 7. |
| `perrier/` | Bản sao Perrier (`dd09dad`). Test của Perrier chạy riêng bằng pytest. |
| `advanced/` | Phần nâng cao (ADVANCED.md), tách riêng: `extract` (PDF → text/bảng/hình + ảnh crop), `describe` (mô tả hình bằng vision model), `chunks`, `index` (bảng `adv_chunks`), `benchmark` (kiểm tra bộ câu hỏi), `metrics`, `experiment` (runner, tool `view_figure`). Xem [data/advanced/README.md](../data/advanced/README.md). |
