# Day 7: Agentic RAG trên vector store Day 6

Bài cá nhân của Đậu Phúc Đức (2A202603580), lớp K5-L3A. Đề bài gốc ở [ASSIGNMENT.md](ASSIGNMENT.md).

Agent dùng `gpt-5.4-nano` có tool calling. Agent tự tìm bằng chứng trong 129 chunk của Day 6 (Nghị định 13/2023/NĐ-CP và bài báo "Attention Is All You Need"), rồi trả lời có citation `[chunk-id]` hoặc từ chối khi tài liệu không đủ bằng chứng. Bài so sánh 3 phương pháp retrieval (dense, BM25, hybrid RRF) và 2 cấu hình cải thiện rút ra từ lỗi trên dev, chọn cấu hình theo tiêu chí công bố trước, rồi đánh giá một lần trên test.

**Cấu hình được chọn: `searches-2`**, tức dense retrieval với agent tìm tối đa 2 lượt. Trên test, cấu hình này giữ nguyên chất lượng của baseline nhưng rẻ hơn 29% và có p90 thời gian thấp hơn 2,6 s.

- Báo cáo: [report/individual/2A202603580_DauPhucDuc.md](report/individual/2A202603580_DauPhucDuc.md)
- Tiêu chí chọn (commit trước lần chạy dev đầu tiên): [results/selection_criteria.md](results/selection_criteria.md)
- Lỗi trên dev, giả thuyết, kết quả trước/sau: [results/dev_errors.md](results/dev_errors.md)
- Chốt cấu hình (commit trước khi chạy test): [results/selection.md](results/selection.md)

## Kết quả

**Dev** (15 câu có đáp án, 2 câu thiếu evidence). Hit@1 và Hit@3 đo retrieval không qua agent, bằng câu hỏi gốc. Grounded là nhãn tay, tổng điểm /30.

| Cấu hình | Hit@1 | Hit@3 | Context Evidence | Grounded | Từ chối đúng | Từ chối nhầm | Chi phí/câu | p90 |
|---|---|---|---|---|---|---|---|---|
| `dense` (baseline) | 10/15 | 15/15 | 15/15 | 28 | 2/2 | 0/15 | $0.00082 | 5.32 s |
| `bm25` | 12/15 | 14/15 | 15/15 | 30 | 2/2 | 0/15 | $0.00101 | 4.80 s |
| `hybrid` | 11/15 | 15/15 | 15/15 | 25 | 2/2 | 2/15 | $0.00094 | 5.16 s |
| `answer-rules` | 10/15 | 15/15 | 15/15 | 29 | 2/2 | 0/15 | $0.00104 | 5.57 s |
| **`searches-2`** | 10/15 | 15/15 | 15/15 | 28 | 2/2 | 0/15 | **$0.00070** | **3.57 s** |

**Test** (5 câu có đáp án, 2 câu thiếu evidence). Chạy một lần, sau commit `ed0a0ad` chốt cấu hình. Grounded là tổng điểm /10. Nhãn context của cả 10 lượt đều ở mức 2.

| Cấu hình | Hit@1 | Hit@3 | Context Evidence | Grounded | Từ chối đúng | Từ chối nhầm | Chi phí/câu | p90 |
|---|---|---|---|---|---|---|---|---|
| `dense` (baseline) | 5/5 | 5/5 | 5/5 | 10/10 | 2/2 | 0/5 | $0.00116 | 6.31 s |
| **`searches-2`** | 5/5 | 5/5 | 5/5 | 10/10 | 2/2 | 0/5 | **$0.00082** | **3.75 s** |

Không có lỗi model hay vector store ở lần chạy nào. Chi tiết, nhãn và giới hạn ở báo cáo.

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| `src/retrievers.py` | Dense (pgvector, cosine exact), BM25 (âm tiết + bigram tiếng Việt), hybrid RRF. Filter áp trước khi xếp hạng. |
| `src/agent.py` | Vòng lặp agent: tool `search`, `answer`, `abstain`; ngữ cảnh 2.000 token (`tiktoken o200k_base`); kiểm tra citation; thử lại khi lỗi API. |
| `src/experiment.py` | Runner thí nghiệm, danh sách cấu hình, chặn split test khi `results/selection.md` chưa commit. |
| `src/metrics.py` | Metric tự động: Hit@1, Hit@3, Context Evidence, tool use, từ chối, thời gian, chi phí. |
| `src/labels.py` | Bảng nhãn tay (CSV) và script tổng hợp nhãn. |
| `src/demo.py` | Lệnh demo: một câu có bằng chứng, một câu thiếu bằng chứng, một lỗi. |
| `src/benchmark.py` | Chuyển chunk Day 6 sang schema Day 7; kiểm tra bộ câu hỏi. |
| `src/parse_docs.py`, `src/index.py`, `src/check_index.py` | Đọc và chunk tài liệu, nạp pgvector, đối chiếu index với Day 6 (chép từ Day 6). |
| `src/perrier/` | Bản sao đầy đủ của Perrier (`dd09dad`), dùng để đọc tài liệu và embedding. |
| `data/` | `chunks.json` (129 chunk), `questions.json` (24 câu), `manifest.json` (nguồn, quyền), `parsed/`, `ocr/`. |
| `results/` | Trace và summary của mọi lần chạy, nhãn tay, tiêu chí, lỗi dev, cấu hình chốt. |
| `tests/` | 54 test `unittest` (model và retriever giả, không gọi API). |

## Chạy lại

Cần: Python 3.11 và [uv](https://docs.astral.sh/uv/), Docker, [Ollama](https://ollama.com/), và một OpenAI API key. Lệnh dưới đây chạy được trong PowerShell lẫn Git Bash.

```bash
uv sync                                  # cài thư viện (torch bản CPU)
cp .env.example .env                     # rồi điền OPENAI_API_KEY; các giá trị khác đã có mặc định
docker compose up -d                     # Postgres + pgvector của lab, cổng 55434
ollama pull embeddinggemma-2             # embedding 768 chiều, như Day 6
uv run python -m src.check_setup         # kiểm tra môi trường; không in giá trị bí mật
uv run python -m src.index --approve e6054dd139ec   # nạp 129 chunk đã duyệt ở Day 6 vào pgvector (~2 phút)
uv run python -m src.benchmark verify    # kiểm tra 24 câu với chunk và trang
uv run python -m unittest discover -s tests
```

Fingerprint `e6054dd139ec` là của bản parse Day 6 đã duyệt. `data/parsed/` được chép nguyên từ Day 6, nên index dựng lại giống hệt Day 6: [results/index_check.json](results/index_check.json) cho thấy cả 129 chunk trùng text, trùng model, cosine giữa hai vector bằng 1.

Thí nghiệm (mỗi lệnh ghi `results/<loại>/<tên>/<split>/{traces,summary}.json`):

```bash
uv run python -m src.experiment retrieval --method dense --split dev     # dense | bm25 | hybrid
uv run python -m src.experiment agent --config dense --split dev         # dense | bm25 | hybrid | answer-rules | searches-2
uv run python -m src.experiment agent --config dense --split dev --ids q01,u01   # chạy thử, ghi vào dev-smoke (gitignore)
uv run python -m src.labels export --split dev       # tạo/cập nhật bảng nhãn, giữ nhãn đã duyệt
uv run python -m src.labels summarize --split dev    # tổng hợp nhãn tác giả -> results/labels/summary_dev.json
```

Split `test` bị runner từ chối cho tới khi `results/selection.md` đã được commit. Chạy lại agent cho kết quả hơi khác vì model không tất định; trace đã commit là kết quả được báo cáo. Chi phí một lần chạy agent trên dev khoảng $0.012–0.018.

Demo (khoảng $0.002):

```bash
uv run python -m src.demo                                         # 3 ví dụ: có bằng chứng, thiếu bằng chứng, một lỗi
uv run python -m src.demo --ask "Nghị định 13 có hiệu lực từ ngày nào?"
uv run python -m src.demo --ask "Hồ sơ phải gửi trong bao lâu?" --chapter "Chương II"
```

## Dữ liệu

| Tài liệu | Trang dùng | Quyền sử dụng |
|---|---|---|
| Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân (bản scan ký số, Cổng TTĐT Chính phủ) | 1–28 / 39 | Văn bản quy phạm pháp luật, không thuộc đối tượng bảo hộ quyền tác giả (Điều 15 Luật SHTT) |
| Vaswani et al., "Attention Is All You Need" ([arXiv:1706.03762](https://arxiv.org/abs/1706.03762)) | 1–10 / 15 | arXiv non-exclusive license; dùng cho học thuật, giữ ghi nguồn |

- Tổng cộng 38 trang nội dung. Chunk theo heading: 129 chunk (84 nd13, 45 aiayn), embedding `embeddinggemma-2` 768 chiều qua Ollama.
- PDF gốc không commit (`data/raw/` bị gitignore). Dựng lại index không cần PDF: OCR và kết quả parse đã có trong `data/ocr/` và `data/parsed/`. Chỉ cần PDF khi muốn parse lại; nguồn và sha256 ghi ở [data/manifest.json](data/manifest.json).
- Benchmark lấy 20 câu có evidence từ Day 6 (giữ nguyên split 15 dev / 5 test). Thêm 4 câu thiếu evidence u01–u04, mỗi câu có `absence_reason` và regex kiểm tra trên toàn bộ trang (`src/benchmark.py verify`).

## Nguồn code và cách dùng AI

- Phần đọc tài liệu, chunk, index và đối chiếu được chép từ bài Day 6 của tác giả (commit `646216f`). Perrier là dự án riêng của tác giả, chép đầy đủ vào `src/perrier` (commit `dd09dad`) để repo tự chạy được.
- Code, tài liệu và nhãn gợi ý được viết với sự hỗ trợ của Claude Code (trợ lý lập trình, gọi là "Mr Duke" trong các file kết quả). Tác giả quyết định thiết kế, tiêu chí và cấu hình, duyệt nhãn, và chịu trách nhiệm về code và số liệu (`RULES.md`).
- `.env`, API key và PDF gốc không được commit.
