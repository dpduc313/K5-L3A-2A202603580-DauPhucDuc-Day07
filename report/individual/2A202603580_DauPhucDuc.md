# Báo cáo Day 7

Họ và tên: Đậu Phúc Đức

MSSV: 2A202603580

Repo: `dpduc313/K5-L3A-DAY07-2A202603580-DauPhucDuc-RetrievalContext`. Cách chạy lại ở [README](../../README.md).

## Dữ liệu và benchmark

- **Nguồn, quyền sử dụng, số trang và số chunk.** Dùng lại corpus Day 6: 38 trang nội dung từ hai tài liệu.
  - Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân: trang 1–28 trên 39, bản scan ký số của Cổng TTĐT Chính phủ. Văn bản quy phạm pháp luật nên không thuộc đối tượng bảo hộ quyền tác giả.
  - Vaswani et al., "Attention Is All You Need": trang 1–10 trên 15, arXiv non-exclusive license, dùng cho học thuật và giữ ghi nguồn.

  Chunk theo heading như Day 6: 129 chunk (84 nd13, 45 aiayn), dài trung vị 642 ký tự. Nguồn, sha256 và quy tắc tính trang ghi ở `data/manifest.json`.
- **Vector store, embedding model, phiên bản và số chiều.**
  - Vector store: Postgres 16 + pgvector 0.8.7 (`pgvector/pgvector:0.8.7-pg16`), database riêng `day7_lab` ở cổng 55434, bảng `lab_chunks`. Tìm cosine exact, không dùng index HNSW: corpus nhỏ, và filter metadata không làm thiếu kết quả.
  - Embedding: `embeddinggemma-2` qua Ollama, 768 chiều; query có prefix như lúc Day 6 embed tài liệu.
  - Index được dựng lại từ đúng bản parse Day 6 đã duyệt (fingerprint `e6054dd139ec`). `results/index_check.json` đối chiếu với database Day 6: 129/129 chunk trùng `text_sha256`, trùng model, cosine giữa hai vector bằng 1.
- **Agent model, cách chạy và phân chia dev/test.**
  - Model: `gpt-5.4-nano` (`gpt-5.4-nano-2026-03-17`) qua `langchain-openai`, `reasoning_effort=none`, `tool_choice=required`.
  - Chạy: `python -m src.experiment agent --config <cấu hình> --split <split>`.
  - Benchmark 24 câu. Dev: 15 câu có đáp án + 2 câu thiếu evidence (u01, u02). Test: 5 câu có đáp án + 2 câu thiếu evidence (u03, u04).
  - 20 câu có đáp án lấy từ Day 6, giữ nguyên split. Test Day 6 chỉ chạy một lần sau khi chốt, không dùng để chỉnh, và giảng viên xác nhận được dùng lại.
  - 5 câu có filter `chapter` (q06, q09, q11, q15, q16). Filter coi là thông tin người dùng cho: runner truyền thẳng vào tool, model không đổi được.
- **Cách xác định câu có/thiếu evidence và tiêu chí chấm.**
  - Câu có đáp án: mỗi `gold` là `{source_id, page, evidence}`. Một chunk "chứa evidence" khi đúng nguồn, đúng trang và `normalize(evidence)` nằm trọn trong text. `python -m src.benchmark verify` kiểm tra mọi gold có trong ít nhất một chunk, và với câu có filter thì chunk đó thỏa filter.
  - Câu thiếu evidence: chọn câu gần chủ đề (mức phạt tiền, chi phí huấn luyện bằng đô la, lệ phí thẩm định, tốc độ suy luận). Mỗi câu có `absence_reason` và regex chạy trên **toàn bộ trang**, không chỉ top-k, để chứng minh tài liệu không có thông tin đó. Tác giả duyệt từng câu.
  - Tiêu chí chấm và thứ tự chọn được commit trước lần chạy dev đầu tiên: `results/selection_criteria.md`.

## Retrieval và thử nghiệm

Chung cho mọi cấu hình agent: `gpt-5.4-nano`; top-5 mỗi lượt; context budget 2.000 token (`tiktoken o200k_base`), bỏ chunk trùng giữa các lượt và giữ chunk score cao nhất khi vượt budget; filter của người dùng áp trước khi xếp hạng; không rerank.

Định nghĩa các cột:
- **Hit@1, Hit@3**: retrieval không qua agent, bằng câu hỏi gốc, top-3.
- **Context Evidence**: ngữ cảnh cuối gửi model có chunk chứa evidence.
- **Thời gian / chi phí**: trung vị giây mỗi câu của agent (đầu tới cuối), và USD mỗi câu theo usage API × giá `gpt-5.4-nano` (0,20 / 1,25 USD mỗi triệu token vào/ra). Embedding chạy local, tính 0.

| Cấu hình | Phương pháp, top-k, filter, rerank, context budget | Giả thuyết / thay đổi | Split | Hit@1 | Evidence Hit@3 | Context Evidence Rate | Thời gian / chi phí |
|---|---|---|---|---|---|---|---|
| Baseline `dense` | Dense cosine exact, top-5, filter người dùng, không rerank, 2.000 token, tối đa 4 lượt | Phương pháp 1 | dev | 10/15 (0,67) | 15/15 (1,00) | 15/15 (1,00) | 2,65 s / $0.00082 |
| Phương pháp 2 `bm25` | BM25 (k1 = 1,5; b = 0,75), âm tiết + bigram âm tiết tiếng Việt; còn lại như baseline | Từ khóa chính xác (số hiệu, thuật ngữ luật) xếp hạng tốt hơn embedding | dev | 12/15 (0,80) | 14/15 (0,93) | 15/15 (1,00) | 2,33 s / $0.00101 |
| Phương pháp 3 `hybrid` | RRF (k = 60) của top-20 dense và top-20 BM25; còn lại như baseline | Gộp ưu điểm của hai phương pháp | dev | 11/15 (0,73) | 15/15 (1,00) | 15/15 (1,00) | 2,33 s / $0.00094 |
| Cải thiện 1 `answer-rules` | Như baseline + quy tắc 6 trong system prompt | Giữ đủ điều kiện và ngoại lệ (lỗi 3) | dev | 10/15 (0,67) | 15/15 (1,00) | 15/15 (1,00) | 2,35 s / $0.00104 |
| Cải thiện 2 `searches-2` | Như baseline, tối đa **2** lượt search | Bỏ lượt tìm lặp ở câu thiếu evidence (lỗi 4) | dev | 10/15 (0,67) | 15/15 (1,00) | 15/15 (1,00) | 2,43 s / $0.00070 |
| Cấu hình đã chọn `searches-2` | như trên | | test | 5/5 (1,00) | 5/5 (1,00) | 5/5 (1,00) | 3,58 s / $0.00082 |
| Baseline `dense` | như trên | | test | 5/5 (1,00) | 5/5 (1,00) | 5/5 (1,00) | 4,61 s / $0.00116 |

Ghi chú bảng:
- Hai cấu hình cải thiện không đổi retrieval, nên Hit@1/Hit@3 bằng của `dense`. Không có phương pháp retrieval nào kiêm cải thiện; 5 cấu hình được đo riêng.
- Với 3 câu có filter trong dev (q06, q09, q15) và 2 câu trong test (q11, q16), Hit@3 giống nhau khi có và không có filter (`filter_questions` trong summary retrieval).

**Hai lỗi dev, nguyên nhân, cách thử** (đầy đủ ở `results/dev_errors.md`, gồm 5 lỗi):

1. **Agent từ chối trước khi tìm** (`hybrid` q10, lần chạy đầu).
   - Hiện tượng: lượt đầu, model được chọn cả `abstain` khi ngữ cảnh còn trống, và đã từ chối với 0 lượt search.
   - Sửa: lượt đầu chỉ đưa tool `search`. Đây là sửa lỗi chung cho mọi cấu hình, có test riêng, rồi chạy lại cả 3 phương pháp.
   - Sau khi sửa: 0/85 lượt chạy kết thúc với 0 search; Context Evidence của `hybrid` từ 14/15 lên 15/15.
2. **Câu trả lời bỏ vế điều kiện có sẵn trong chunk được trích** (q02, q07 ở cả 3 phương pháp).
   - Hiện tượng: q02 chỉ nêu "đủ 7 tuổi", bỏ "và có sự đồng ý của cha, mẹ hoặc người giám hộ". q07 bỏ ngoại lệ của doanh nghiệp trực tiếp kinh doanh xử lý dữ liệu.
   - Nguyên nhân: evidence đã đứng hạng 1 trong ngữ cảnh, nên đây không phải lỗi retrieval mà là lỗi viết câu trả lời.
   - Thử: ứng viên `answer-rules` thêm quy tắc giữ đủ điều kiện và ngoại lệ. Kết quả: sửa được q07, không sửa được q02; grounded 29/30 so với 28/30; chi phí +27% vì agent tìm nhiều hơn. Giả thuyết đúng một phần.
3. Lỗi thứ ba dẫn tới cấu hình được chọn: **lượt tìm lặp ở câu thiếu evidence**.
   - Hiện tượng: cả 3 phương pháp đều dùng đủ 4 lượt với truy vấn gần như trùng nhau; lượt 3–4 hầu như không thêm chunk mới. Hai câu này chiếm 26–30% chi phí dev.
   - Thử: `searches-2` giảm chi phí của chúng 45%, chất lượng không đổi.

Ba ứng viên công bố trước (rerank, query transform, context 4.000 token) bị thay vì nhắm vào retrieval, trong khi dev cho thấy retrieval đã bão hòa: Hit@3 15/15 và Context Evidence 15/15. Việc thay được ghi kèm lý do và ngày ở mục "Thay đổi" của `selection_criteria.md`, trước khi chạy ứng viên.

**Lý do chọn cấu hình** (`results/selection.md`). Thứ tự ưu tiên: Context Evidence → grounded → hành vi từ chối → Hit@3 → chi phí/thời gian.
- Cả 5 cấu hình hòa ở Context Evidence. `bm25` cao nhất ở grounded (30/30), nên X = `bm25`.
- Quy tắc hòa: Y rẻ hơn X và kém X không quá 1 câu ở tiêu chí 1 và 3, không quá 2 điểm grounded ở tiêu chí 2.
  - Cách hiểu "2 điểm grounded" được tác giả chốt **sau khi** thấy nhãn gợi ý, và ghi rõ như vậy. Cách hiểu khác ("Y bị chấm thấp hơn ở không quá 1 câu") sẽ chọn `bm25`.
- Theo quy tắc này, `dense` và `searches-2` ngang `bm25`, và `searches-2` rẻ nhất.
- Hai điểm `bm25` hơn đến từ q02 và q07. Đây là lỗi viết câu trả lời, và ở lần chạy trước khi sửa `bm25` cũng bỏ vế cha mẹ ở q02, nên phần hơn này có khả năng là nhiễu.

## Agent và đánh giá

- **Tool, số lượt gọi, điều kiện dừng, cách chọn context và xử lý lỗi:**
  - Ba tool:
    - `search(query)` gọi retriever của cấu hình, kèm filter người dùng;
    - `answer(answer, citations)`;
    - `abstain(reason, citations)`.
  - Lượt đầu chỉ có `search`; hết lượt search thì chỉ còn `answer`/`abstain`.
  - Dừng khi model gọi `answer` hoặc `abstain`; hết lượt mà chưa có action cuối thì tính là từ chối.
  - Ngữ cảnh: mỗi lượt gộp kết quả vào kho ứng viên (bỏ trùng theo ID, giữ score cao nhất), rồi đóng gói lại theo score cho tới 2.000 token. Model nhận lại system prompt cùng một khối `<context>` có ID, nguồn và trang của từng chunk; nội dung tài liệu được đánh dấu là dữ liệu, không phải chỉ dẫn.
  - Citation hợp lệ khi ID có trong ngữ cảnh **và** `[ID]` xuất hiện trong câu trả lời; sai thì kết quả là từ chối.
  - Lỗi API (mạng, 429, 5xx): thử lại 3 lần, chờ 2/4/8 s; vẫn lỗi thì `status: error`, giữ thông báo lỗi, không có kết quả thay thế. Không lần chạy nào bị lỗi.

Định nghĩa các cột: grounded là số câu ở mức 2/1/0 kèm trung bình /2; citation hợp lệ đếm trên citation của các câu trả lời. Nhãn của tác giả nằm ở `results/labels/`. Ở dev, tác giả duyệt 166 dòng, giữ nguyên toàn bộ nhãn gợi ý của trợ lý (0 dòng sửa). Ở test, tác giả duyệt 35 dòng (14 câu trả lời, 11 citation, 10 context), cũng giữ nguyên toàn bộ gợi ý.

| Cấu hình / split | Tool use | Số lượt gọi | Grounded answer 0/1/2 và trung bình | Citation hợp lệ | Câu có citation | Abstention đúng | Từ chối nhầm |
|---|---|---|---|---|---|---|---|
| `dense` / dev | 17/17 | 1×13, 2×2, 4×2 | 13 / 2 / 0 → 1,87 | 16/16 | 15/15 | 2/2 | 0/15 |
| `bm25` / dev | 17/17 | 1×11, 2×2, 3×2, 4×2 | 15 / 0 / 0 → 2,00 | 17/17 | 15/15 | 2/2 | 0/15 |
| `hybrid` / dev | 17/17 | 1×12, 2×2, 4×3 | 12 / 1 / 2 → 1,67 | 14/14 | 13/13 | 2/2 | 2/15 |
| `answer-rules` / dev | 17/17 | 1×11, 2×2, 4×4 | 14 / 1 / 0 → 1,93 | 17/17 | 15/15 | 2/2 | 0/15 |
| `searches-2` / dev | 17/17 | 1×14, 2×3 | 13 / 2 / 0 → 1,87 | 17/17 | 15/15 | 2/2 | 0/15 |
| `dense` / test | 7/7 | 1×4, 2×1, 4×2 | 5 / 0 / 0 → 2,00 | 5/5 | 5/5 | 2/2 | 0/5 |
| `searches-2` / test | 7/7 | 1×5, 2×2 | 5 / 0 / 0 → 2,00 | 6/6 | 5/5 | 2/2 | 0/5 |

Nhãn context trên test (0/1/2, `results/labels/context.csv`, 5 câu có đáp án mỗi cấu hình): `dense` 5 câu mức 2, `searches-2` 5 câu mức 2, không câu nào mức 0 hay 1. Ngữ cảnh cuối của cả 10 lượt chạy chứa đủ evidence, gồm cả câu cần hai vế (q04: thời hạn 72 giờ và vế thông báo muộn; q16: giá trị label smoothing và hai tác động), kèm nguồn và trang.

| Query ID | Loại câu | Tool call và kết quả | Câu trả lời và citation | Nhãn, lý do |
|---|---|---|---|---|
| q10 (`searches-2`, dev) | Có đáp án | 1 search "xóa dữ liệu cá nhân theo yêu cầu của chủ thể dữ liệu phải thực hiện…"; `nd13-heading-0036` (tr. 14) hạng 2 | "… trong 72 giờ kể từ khi có yêu cầu … (trừ trường hợp pháp luật có quy định khác). [nd13-heading-0036]" | 2: đúng 72 giờ; citation hợp lệ |
| u01 (`searches-2`, dev) | Thiếu evidence | 2 search về "phạt tiền tối đa", cùng top-5 (`nd13-heading-0000`, `0046`, `0010`, `0070`, `0047`) | Từ chối: không có điều khoản về mức phạt tiền; chỉ có Điều 23 (thông báo vi phạm) và Điều 4 (nguyên tắc xử lý chung) | 1: từ chối đúng, không đưa con số |
| q02 (`searches-2`, dev) | Có đáp án, **lỗi** | 2 search; `nd13-heading-0042` (tr. 16) hạng 1 ở cả hai lượt | "… phải có sự đồng ý của chính trẻ em trong trường hợp trẻ em từ đủ 7 tuổi trở lên. [nd13-heading-0042]" | 1: bỏ vế "và có sự đồng ý của cha, mẹ hoặc người giám hộ" dù vế này nằm trong câu được trích |
| q03 (`hybrid`, dev) | Có đáp án, **lỗi** | 1 search; `nd13-heading-0023` trong ngữ cảnh | Câu trả lời đúng ("Không …") nhưng không viết `[nd13-heading-0023]` trong văn bản, nên luật citation chuyển thành từ chối | 0: từ chối câu có đáp án (lỗi 5) |
| u03 (`dense`, test) | Thiếu evidence | 4 search gần như trùng nhau về "lệ phí thẩm định" | Từ chối: không có quy định về lệ phí thẩm định | 1: từ chối đúng, không suy diễn từ "kinh phí" hay "chi phí" ở các điều khác. Lượt 2–4 lặp truy vấn, giống lỗi 4 ở dev (`searches-2` chỉ dùng 2 lượt cho câu này) |

- **Đường dẫn trace, nhãn, lệnh chạy, thời gian và chi phí:**
  - Trace: `results/agent/<cấu hình>/<split>/traces.json` (mỗi câu có mọi model call, tool call, query, top-5 kèm score và hạng, ngữ cảnh cuối, câu trả lời, citation, token, chi phí, thời gian). Summary: `summary.json`.
  - Retrieval không qua agent: `results/retrieval/<phương pháp>/<split>/`. Bản chạy trước khi sửa lỗi 1–2: `results/agent/_before_fix/`.
  - Nhãn: `results/labels/{answers,citations,context}.csv`; tổng hợp ở `results/labels/summary_<split>.json`.
  - Lệnh chạy và demo: README.
  - Chi phí các lần chạy được báo cáo: dev 8 lượt chạy agent × 17 câu, tổng $0.121 (3 lượt trước khi sửa + 5 lượt sau khi sửa); test 2 lượt, tổng $0.014. Chưa tính các lần chạy thử (`--ids`) và lần chạy dense đầu tiên ở C3 (code chưa commit, $0.014).
- **Kết quả trước/sau, ví dụ lỗi, đánh đổi và giới hạn:**
  - **Test, chạy một lần sau khi chốt** (`ed0a0ad`):
    - `searches-2` và `dense` như nhau về chất lượng: grounded 10/10, context mức 2 ở cả 5 câu, từ chối đúng 2/2, không từ chối nhầm.
    - `searches-2` rẻ hơn 29% ($0.00082 so với $0.00116 mỗi câu), p90 3,75 s so với 6,31 s; phần giảm đến chủ yếu từ u03 và u04.
    - Test chỉ có 5 câu có đáp án và retrieval đạt Hit@1 5/5, nên test không phân biệt được chất lượng giữa hai cấu hình. Nó chỉ xác nhận rằng giảm số lượt tìm không làm giảm chất lượng trên các câu này.
  - **Trước/sau sửa lỗi chung:** sai ngôn ngữ (câu hỏi tiếng Anh trả lời tiếng Việt) từ 9/18 xuống 0/18; từ chối khi chưa tìm từ 1 xuống 0; Context Evidence của `hybrid` từ 14/15 lên 15/15.
  - **Đánh đổi:**
    - `searches-2` giữ nguyên chất lượng của baseline, nhưng chi phí giảm 15% trên dev và 29% trên test, p90 giảm 1,75 s trên dev và 2,6 s trên test.
    - `bm25` có grounded cao nhất nhưng đắt hơn 23% so với `dense` và Hit@3 kém một câu (q03).
    - `answer-rules` sửa một phần lỗi điều kiện nhưng đắt hơn 27%.
  - **Giới hạn:**
    - Dev chỉ có 15 câu có đáp án và mỗi cấu hình chạy một lần; model không tất định (lỗi ngôn ngữ từng dao động giữa các lần chạy), nên chênh 1–2 câu nằm trong vùng nhiễu.
    - Retrieval trên corpus 129 chunk đã bão hòa, nên bộ câu hỏi này không phân biệt được các phương pháp retrieval ở Context Evidence.
    - `searches-2` chưa được thử với câu cần từ 3 lượt tìm trở lên.
    - Lỗi 5: luật citation chặt chuyển câu trả lời đúng thành từ chối khi model quên viết `[ID]` trong văn bản (2/85 lượt ở dev). Không sửa vì luật đã công bố trước. Hướng sửa: trả lỗi cho model và cho thử lại một lần.
    - Lỗi 3 (q02) chưa sửa được.
    - Nhãn grounded và citation dựa trên một người chấm, có gợi ý của trợ lý AI.

## Thử thách nâng cao (nếu thực hiện)

Không thực hiện.
