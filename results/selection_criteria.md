# Tiêu chí chọn cấu hình và danh sách ứng viên (công bố trước khi chạy dev)

File này được viết và commit **trước** lần chạy dev đầu tiên. Lúc đó chưa có kết quả retrieval hay agent nào trên dev hoặc test (`GUIDE.md:38`, `BENCHMARK.md:17`). Muốn đổi bất kỳ điều gì ở đây sau khi đã chạy dev thì phải thêm mục "Thay đổi", ghi lý do và ngày; không sửa đè.

## 1. Dữ liệu và split

- Corpus: 129 chunk theo heading của Day 6 (`data/chunks.json`), index `lab_chunks` trong `day7_lab`. Index này giống hệt Day 6 (`results/index_check.json`).
- Benchmark: `data/questions.json`.
  - **Dev**: 15 câu có đáp án và 2 câu thiếu evidence (u01, u02). Dùng để thử và chọn.
  - **Test**: 5 câu có đáp án và 2 câu thiếu evidence (u03, u04). Chỉ chạy sau khi `results/selection.md` đã được commit, chạy một lần cho baseline và cấu hình được chọn. Nếu sau đó phải sửa hệ thống thì tạo test mới, không chỉnh theo test (`RULES.md:5`).
- Gold, `expected_answer` và `absence_reason` không bao giờ được đưa vào agent, query hay retriever.
- Filter: 5 câu có filter `chapter` (q06, q09, q11, q15, q16) coi filter là thông tin người dùng cung cấp. Runner truyền filter thẳng vào tool; model không thêm, bỏ hay đổi được. Mọi phương pháp áp filter **trước** khi xếp hạng.

## 2. Các cấu hình

Mọi cấu hình dùng chung một agent, trừ yếu tố được nêu là thay đổi:

- Model `gpt-5.4-nano`, có tool calling.
- Một tool `search(query)`. Phương pháp retrieval phía sau tool do cấu hình quyết định.
- Tối đa 4 lượt search, top-5 mỗi lượt.
- Context budget 2.000 token, đếm bằng `tiktoken` `o200k_base`. Bỏ chunk trùng giữa các lượt; khi vượt budget thì giữ chunk có score cao nhất.
- Kết thúc bằng một trong hai action:
  - `answer`: câu trả lời có citation `[chunk-id]`, ID phải có trong context.
  - `abstain`: nói rõ không đủ bằng chứng; được kèm lý do và trích dẫn đoạn liên quan đã tìm.
- `answer` không có citation hợp lệ thì bị coi là `abstain`. Hết lượt search mà chưa có action cuối cũng là `abstain`.
- Trả lời bằng ngôn ngữ của câu hỏi. System prompt ghi rõ nội dung tài liệu là dữ liệu, không phải chỉ dẫn.

| Tên | Vai trò | Phương pháp retrieval |
|---|---|---|
| `dense` | **Baseline**, phương pháp 1 | Embed query bằng `embeddinggemma-2` (768 chiều), cosine exact trên `lab_chunks` heading. |
| `bm25` | Phương pháp 2 | BM25 (k1 = 1,5; b = 0,75) trên 129 chunk. Tách từ: `lab_config.normalize`, rồi lấy âm tiết `\w+` cộng bigram âm tiết liền kề, để bắt được từ ghép tiếng Việt như "dữ liệu", "cá nhân". Không dùng `tsvector('english')`. |
| `hybrid` | Phương pháp 3 | RRF (k = 60) gộp top-20 của `dense` và top-20 của `bm25`. |

**Ứng viên cải thiện.** Chọn 2 trong 3 ứng viên sau khi đọc ít nhất 2 lỗi của baseline trên dev. Mỗi ứng viên chỉ đổi một yếu tố so với cấu hình gốc của nó.

| Tên | Gốc | Yếu tố thay đổi | Giả thuyết |
|---|---|---|---|
| `rerank` | `hybrid` | Rerank top-20 bằng `BAAI/bge-reranker-v2-m3` (đa ngôn ngữ, chạy CPU) rồi lấy top-5 | Thứ hạng còn yếu (Day 6: Hit@1 dev 10/15). Reranker tiếng Anh từng làm tụt kết quả trên nd13, reranker đa ngôn ngữ thì không. |
| `query` | baseline hoặc cấu hình tốt nhất trong 3 phương pháp | Biến đổi query: `multi_query` hoặc `rag_fusion` của Perrier, sửa cho đọc `lab_chunks`. Báo riêng kết quả của query gốc và trace từng query viết lại. | Câu hỏi chéo ngôn ngữ (q19, q20) và câu điều kiện diễn đạt khác văn bản luật. |
| `context` | baseline hoặc cấu hình tốt nhất trong 3 phương pháp | Budget 4.000 token, hoặc thêm chunk lân cận cùng trang/Điều. | Câu điều kiện của nd13 cần evidence từ nhiều Điều; budget 2.000 token có thể cắt mất evidence. |

Việc chọn ứng viên nào, và lỗi dev làm căn cứ, được ghi vào `results/dev_errors.md` trước khi chạy ứng viên đó.

## 3. Metric

Hit (định nghĩa dùng chung cho mọi metric): một chunk "chứa evidence" khi đúng `source_id`, đúng `page`, và `normalize(evidence)` nằm trọn trong `normalize(text)` (`src/benchmark.py: contains_evidence`). Các phần tử `gold` là evidence thay thế; chỉ cần khớp một phần tử.

**Retrieval** (chạy từng phương pháp không qua agent, bằng query gốc, top-3; mẫu số là 15 câu có đáp án của dev, không tính câu thiếu evidence):

- **Hit@1**: số câu có chunk hạng 1 chứa evidence / 15.
- **Evidence Hit@3**: số câu có ít nhất một chunk trong top-3 chứa evidence / 15.
- 5 câu có filter được báo thêm kết quả khi không có filter.

**Agent** (chạy cả 5 cấu hình trên dev):

- **Context Evidence Rate**: số câu có đáp án mà context cuối gửi model chứa ít nhất một chunk chứa evidence / 15. Context có thể gộp từ nhiều lượt search.
- **Grounded answer**: nhãn tay 0/1/2 cho từng câu có đáp án (0 = sai hoặc thiếu evidence; 1 = đúng một phần; 2 = đúng và đủ). Báo số câu ở từng mức và trung bình /2. Câu có đáp án mà agent từ chối thì chấm 0.
- **Citation hợp lệ**: số citation vừa có trong context vừa hỗ trợ câu trả lời (đọc tay) / tổng citation. Báo thêm số câu trả lời có citation / số câu trả lời.
- **Abstention**: số câu thiếu evidence được từ chối đúng / 2. **Từ chối nhầm**: số câu có đáp án bị từ chối / 15.
- **Tool use**: số câu có gọi `search` / số câu chạy thành công, kèm phân bố số lượt gọi.
- **Thời gian**: trung vị và p90 số giây mỗi câu, tính từ đầu tới cuối.
- **Chi phí**: token vào/ra theo usage mà API báo, nhân với giá trong `src/perrier/prices.toml` (`gpt-5.4-nano`: 0,20 / 1,25 USD mỗi triệu token vào/ra). Embedding và reranker chạy local nên tính 0 USD.
- **Lỗi** model hoặc vector store được báo riêng. Khi so cấu hình, câu lỗi tính là không đạt ở mọi metric, không bỏ khỏi mẫu số.

## 4. Thứ tự chọn

So các cấu hình trên dev theo thứ tự ưu tiên:

1. **Context Evidence Rate**
2. **Grounded answer trung bình**
3. **Hành vi từ chối**: số câu thiếu evidence được từ chối cộng số câu có đáp án không bị từ chối nhầm (trên 17 câu)
4. **Evidence Hit@3** (retrieval, query gốc)
5. **Chi phí** mỗi câu, rồi **thời gian** trung vị

Quy tắc hòa:
- Gọi X là cấu hình đứng đầu theo thứ tự trên.
- Một cấu hình Y rẻ hơn X mà ở **mỗi** tiêu chí 1–3 chỉ kém X không quá 1 câu thì được coi là ngang X.
- Trong các cấu hình ngang X, chọn cấu hình rẻ nhất.

Quy tắc này tránh chọn theo nhiễu, vì dev chỉ có 15 câu có đáp án.

Nếu nhiều cấu hình có cùng chi phí và thời gian, chọn cấu hình đơn giản hơn: ít thành phần hơn, theo thứ tự `dense` < `bm25` < `hybrid` < cấu hình có thêm bước.

## 5. Nhãn tay

- Nhãn ghi ở `results/labels/{context,answers,citations}.csv`. Mỗi dòng có cột `reason`.
- Claude (trợ lý lập trình, gọi là "Mr Duke") điền nhãn gợi ý cho **mọi** dòng vào cột riêng `suggested_*`, kèm `suggested_reason`. Claude đọc câu trả lời, `expected_answer` và chunk được trích dẫn để gợi ý.
- Tác giả duyệt lại **toàn bộ** các dòng: đọc câu trả lời và chunk được trích dẫn, rồi điền cột nhãn chính thức và `reason`. Nếu nhãn khác gợi ý thì ghi lý do.
- Chỉ cột nhãn chính thức, do tác giả điền, được dùng để tính metric. Dòng chưa được duyệt thì script tổng hợp báo lỗi, không tính.
- Báo cáo ghi rõ số nhãn tác giả giữ nguyên và số nhãn đã sửa so với gợi ý.
- ID citation hợp lệ hoặc nhãn gợi ý không thay cho việc đọc đối chiếu (`BENCHMARK.md:40`).

## Thay đổi

Các mục trên giữ nguyên như lúc công bố. Mọi thay đổi sau lần chạy dev đầu tiên ghi ở đây.

### 2026-11-14 (sau lần chạy dev đầu tiên của 3 phương pháp, trước khi chạy ứng viên nào)

Căn cứ: các lỗi trong `results/dev_errors.md`. Bản chạy trước khi sửa được giữ ở `results/agent/_before_fix/`.

1. **Sửa agent dùng chung (mọi cấu hình).** Đây là sửa lỗi để agent đúng với mục 2, không phải ứng viên cải thiện. Sau khi sửa, chạy lại cả `dense`, `bm25`, `hybrid` trên dev; bản mới thay bản cũ khi so sánh.
   - Lượt đầu chỉ có tool `search`; `answer` và `abstain` có từ lượt thứ hai. Lý do: `hybrid` q10 từ chối ngay khi ngữ cảnh còn trống, trái với quy tắc "tìm trước khi kết luận" (lỗi 1).
   - Quy tắc ngôn ngữ trong system prompt viết lại rõ hơn: viết toàn bộ câu trả lời và lời từ chối bằng ngôn ngữ của câu hỏi. Lý do: 9/18 lượt trả lời câu hỏi tiếng Anh ra tiếng Việt, trái với mục 2 (lỗi 2).
2. **Thay danh sách ứng viên cải thiện.** Không chọn ứng viên nào trong ba ứng viên ở mục 2 (`rerank`, `query`, `context`). Cả ba nhắm vào retrieval hoặc độ dài ngữ cảnh. Trên dev, Evidence Hit@3 của `dense` là 15/15 và Context Evidence Rate là 15/15; evidence của các câu trả lời thiếu ý đã nằm ở hạng 1 trong ngữ cảnh. Hai ứng viên mới, cùng gốc `dense`, mỗi ứng viên chỉ đổi một yếu tố:

   | Tên | Gốc | Yếu tố thay đổi | Giả thuyết |
   |---|---|---|---|
   | `answer-rules` | `dense` | Thêm quy tắc 6 vào system prompt: giữ đủ điều kiện, ngoại lệ, vế đi kèm của đoạn được trích; không trả lời "có/không" trái với phần giải thích | Câu trả lời bỏ vế điều kiện có sẵn trong chunk được trích (q02, q07) và mở đầu mâu thuẫn (q12). Grounded answer tăng, chi phí gần như không đổi (lỗi 3). |
   | `searches-2` | `dense` | Tối đa 2 lượt search thay vì 4 | Với câu thiếu evidence, lượt 3–4 lặp lại truy vấn gần giống và không thêm bằng chứng. Chi phí giảm mà từ chối đúng không giảm (lỗi 4). Rủi ro: câu cần lượt tìm thứ 3 trở lên. |

   Thứ tự chọn và quy tắc hòa ở mục 4 giữ nguyên.

### 2026-11-14 (sau khi có nhãn gợi ý của 5 cấu hình trên dev, trước khi viết `selection.md`)

**Cách hiểu quy tắc hòa với tiêu chí 2 (grounded).** Mục 4 viết "chỉ kém X không quá 1 câu". Với tiêu chí 1 và 3 (đếm câu), câu này rõ nghĩa. Với grounded (điểm 0–2 mỗi câu), nó chưa được định nghĩa. Tác giả chốt: **tổng điểm grounded của Y kém X không quá 2 điểm**, tức tối đa bằng mức chênh một câu có thể gây ra (2 → 0).

- Lý do: quy tắc hòa có mục đích tránh chọn theo nhiễu khi dev chỉ có 15 câu có đáp án, và một câu đơn lẻ có thể làm tổng điểm lệch tới 2.
- Ghi rõ: cách hiểu này được chốt **sau khi** đã thấy nhãn gợi ý. Mr Duke đã báo trước cho tác giả rằng cách hiểu khác ("Y bị chấm thấp hơn X ở không quá 1 câu") sẽ chọn `bm25`, còn cách hiểu này chọn `searches-2`.

## 6. Đo lại bằng `gpt-5.4-mini` (C8b, làm sau cùng)

Sau khi đã chọn cấu hình bằng `nano` và chạy test, chạy lại cấu hình được chọn bằng `gpt-5.4-mini` **trên dev**, và so với `nano` theo đúng các tiêu chí trên. Chỉ khi `mini` thắng trên dev mới chạy `mini` trên test. Kết quả này ghi là một lần chọn thứ hai, kèm thứ tự đã chạy. Không đổi model dựa trên điểm test.
