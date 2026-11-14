# Lỗi trên dev và các thay đổi rút ra

File này ghi các lỗi đọc được trong trace dev, nguyên nhân, thay đổi đã chọn, và kết quả trước/sau. Phần "Lỗi" và "Thay đổi" được viết **trước** khi chạy lại và trước khi chạy hai ứng viên cải thiện (`selection_criteria.md`, mục 2 và mục "Thay đổi"). Phần "Kết quả sau" điền sau khi chạy.

- Model: `gpt-5.4-nano`, `reasoning_effort=none`. Mọi bản chạy dưới đây ở split `dev` (15 câu có đáp án, 2 câu thiếu evidence u01, u02).
- Bản chạy trước khi sửa: `results/agent/_before_fix/{dense,bm25,hybrid}/dev/` (commit code `9402cde`, `dirty: false`).
- Retrieval không qua agent (query gốc): `results/retrieval/{dense,bm25,hybrid}/dev/`.

## Tổng quan trước khi sửa

| Cấu hình | Hit@1 | Evidence Hit@3 | Context Evidence | Từ chối đúng | Từ chối nhầm | Chi phí | Trung vị |
|---|---|---|---|---|---|---|---|
| `dense` | 10/15 | 15/15 | 15/15 | 2/2 | 0/15 | $0.0140 | 2.47 s |
| `bm25` | 12/15 | 14/15 | 15/15 | 2/2 | 0/15 | $0.0168 | 2.53 s |
| `hybrid` | 11/15 | 15/15 | 14/15 | 2/2 | 1/15 | $0.0136 | 2.43 s |

Retrieval gần như bão hòa: `dense` và `hybrid` có evidence trong top-3 ở cả 15 câu, và agent của cả ba phương pháp đều đưa evidence vào ngữ cảnh (trừ một câu do lỗi 1). `bm25` trượt q03 trong top-3 khi dùng query gốc, nhưng agent vẫn tìm được ở lượt đầu với truy vấn tự viết. Các lỗi còn lại nằm ở **cách agent dùng tool và viết câu trả lời**, không nằm ở retrieval.

## Lỗi 1: agent từ chối trước khi tìm (hybrid q10)

- **Hiện tượng.** `hybrid` q10 ("Việc xóa dữ liệu cá nhân theo yêu cầu của chủ thể dữ liệu phải thực hiện trong bao lâu?") kết thúc bằng `abstain` với 0 lượt search, lý do: "Chưa có tài liệu/ngữ cảnh được cung cấp (context trống)". Trace: `_before_fix/hybrid/dev/traces.json`, `events[0].offered_tools = [search, answer, abstain]`. Câu này có đáp án (72 giờ, nd13 tr. 15); `dense` và `bm25` đều trả lời đúng.
- **Nguyên nhân.** Lỗi của vòng lặp agent, không phải của hybrid: lượt đầu model được chọn cả `answer` và `abstain` khi ngữ cảnh còn trống. Quy tắc 1 của prompt ("tìm trước khi kết luận") chỉ là lời dặn, model có thể không theo. Lỗi này có thể xảy ra ở mọi cấu hình; lần này rơi vào `hybrid`.
- **Thay đổi.** Lượt đầu chỉ đưa tool `search`. Test: `tests/test_agent.py: test_first_turn_offers_only_search`. Sửa chung cho mọi cấu hình rồi chạy lại cả ba phương pháp.
- **Kết quả sau** (commit `115daa3`, `results/agent/*/dev/`). Không lượt chạy nào trong 85 lượt (5 cấu hình × 17 câu) kết thúc với 0 lượt search. `hybrid` q10 trả lời đúng 72 giờ sau 1 lượt search; Context Evidence của `hybrid` từ 14/15 lên 15/15.

## Lỗi 2: trả lời sai ngôn ngữ

- **Hiện tượng.** Dev có 6 câu hỏi tiếng Anh (q13, q14, q15, q17, q18, u02). Trước khi sửa, 9/18 lượt trả lời các câu này (6 câu × 3 cấu hình) viết bằng tiếng Việt:
  - `dense`: q17, u02
  - `bm25`: q14, q15, q17, u02
  - `hybrid`: q15, q17, q18

  Không có câu tiếng Việt nào bị trả lời bằng tiếng Anh. Lỗi dao động giữa các lần chạy: ở lần chạy `dense` đầu tiên (C3, code chưa commit), q15 và q18 sai ngôn ngữ; ở lần chạy lại trên commit `9402cde`, hai câu này đúng nhưng q17 sai.
- **Nguyên nhân.** System prompt viết bằng tiếng Việt, còn quy tắc 5 chỉ có một dòng ngắn ("Trả lời bằng ngôn ngữ của câu hỏi."). Ngữ cảnh của các câu này là tiếng Anh, nhưng phần khung tin nhắn (câu hỏi, số lượt còn lại, nhãn NGỮ CẢNH) là tiếng Việt, nên model nghiêng về tiếng Việt.
- **Thay đổi.** Viết lại quy tắc 5: "Viết toàn bộ câu trả lời và lời từ chối bằng đúng ngôn ngữ của câu hỏi: hỏi tiếng Anh thì trả lời tiếng Anh, hỏi tiếng Việt thì trả lời tiếng Việt." Yêu cầu này đã có trong `selection_criteria.md` mục 2, nên đây là sửa lỗi dùng chung, không phải ứng viên. Sai ngôn ngữ không làm giảm nhãn grounded, nên không ảnh hưởng tới việc chọn cấu hình.
- **Kết quả sau.** 0/18 lượt trả lời câu hỏi tiếng Anh của ba phương pháp viết bằng tiếng Việt (trước: 9/18); hai ứng viên cũng 0/12. Lời từ chối u02 của cả 5 cấu hình đều bằng tiếng Anh. Không câu tiếng Việt nào bị trả lời bằng tiếng Anh. Đây là kết quả của một lần chạy; lỗi trước đây dao động giữa các lần chạy, nên một lần chạy sạch chưa chứng minh lỗi đã hết hẳn.

## Lỗi 3: câu trả lời bỏ điều kiện có sẵn trong chunk được trích

- **Hiện tượng.** Cả ba cấu hình đều mắc ở cùng các câu:
  - **q02** (tuổi trẻ em tự đồng ý). Đáp án chuẩn: từ đủ 7 tuổi, **đồng thời** phải có sự đồng ý của cha, mẹ hoặc người giám hộ. Cả ba trả lời "đủ 7 tuổi … đồng ý của chính trẻ em", không nhắc cha mẹ. Chunk được trích `nd13-heading-0042` (tr. 16) có nguyên câu: "phải có sự đồng ý của trẻ em trong trường hợp trẻ em từ đủ 7 tuổi trở lên **và có sự đồng ý của cha, mẹ hoặc người giám hộ** theo quy định".
  - **q07** (doanh nghiệp khởi nghiệp miễn chỉ định bộ phận bảo vệ dữ liệu). Cả ba nêu đúng "02 năm đầu" nhưng bỏ ngoại lệ ở khoản 3 ngay sau đó trong cùng chunk `nd13-heading-0082` (tr. 27): doanh nghiệp "trực tiếp kinh doanh hoạt động xử lý dữ liệu cá nhân **không áp dụng**".
  - **q12** (`dense`): mở đầu "Có." rồi giải thích rằng chỉ được dùng khi có sự đồng ý, tức là đáp án đúng là "Không".
- **Nguyên nhân.** Evidence đã nằm ở hạng 1 trong ngữ cảnh, nên không phải lỗi retrieval hay budget. Model rút gọn câu trả lời về đúng con số được hỏi và bỏ vế điều kiện. Quy tắc 3 hiện chỉ nói "giữ nguyên con số, đơn vị và điều kiện", chưa nêu rõ các vế "đồng thời", "trừ", "không áp dụng".
- **Thay đổi: ứng viên `answer-rules`** (gốc `dense`, chỉ đổi system prompt). Thêm quy tắc 6: "Giữ đủ mọi điều kiện, ngoại lệ và vế đi kèm có trong đoạn được trích (ví dụ các vế "đồng thời", "và có", "trừ trường hợp", "không áp dụng"). Không trả lời "có" hay "không" trái với nội dung giải thích ngay sau đó."
- **Giả thuyết.** Grounded answer tăng ở q02, q07, q12 mà không giảm ở câu khác; chi phí tăng không đáng kể (prompt dài thêm 73 token mỗi lượt gọi model, câu trả lời dài hơn một chút).
- **Kết quả sau** (đọc trace; điểm grounded chờ nhãn của tác giả):
  - q07: `answer-rules` nêu đủ cả ngoại lệ khoản 3, `dense` lần chạy lại vẫn bỏ.
  - q12: `answer-rules` mở đầu đúng "KHÔNG được". Nhưng `dense` lần chạy lại cũng mở đầu "Không.", nên lỗi q12 ở baseline không ổn định và không chứng minh được tác dụng của quy tắc.
  - q02: `answer-rules` **vẫn bỏ** vế cha, mẹ hoặc người giám hộ. Quy tắc không đủ cho trường hợp vế điều kiện nằm giữa câu ("… từ đủ 7 tuổi trở lên và có sự đồng ý của cha, mẹ …").
  - Tác dụng phụ: `answer-rules` tìm nhiều hơn (4 câu dùng đủ 4 lượt, `dense` 2 câu; q09 và q13 dùng 4 lượt dù evidence có từ lượt 1). Chi phí $0.0178 so với $0.0140 của `dense` (+27%), trung vị 2.35 s so với 2.65 s, p90 5.57 s so với 5.32 s.
  - Context Evidence 15/15, từ chối đúng 2/2, từ chối nhầm 0/15, như `dense`.
  - Grounded (nhãn tác giả, `results/labels/summary_dev.json`): `answer-rules` 14 câu đạt 2, 1 câu đạt 1 (q02), trung bình 1.93/2. `dense` 13 câu đạt 2, 2 câu đạt 1 (q02, q07), trung bình 1.87/2. Hơn 1 câu.
  - Kết luận: giả thuyết đúng một phần. Quy tắc sửa được câu có ngoại lệ ở khoản riêng (q07), nhưng không sửa được câu có vế điều kiện nằm giữa câu (q02). Mức hơn 1 câu nằm trong vùng hòa của mục 4, mà chi phí lại cao hơn 27%, nên `answer-rules` không được chọn.

## Lỗi 4: lượt tìm lặp lại không thêm bằng chứng

- **Hiện tượng.** Với 2 câu thiếu evidence, cả ba cấu hình đều dùng đủ 4 lượt search với các truy vấn gần như giống nhau. Ví dụ `dense` u01: "Nghị định 13/2023/NĐ-CP phạt tiền tối đa tổ chức vi phạm…" lặp lại với vài từ đổi chỗ. Số chunk mới mỗi lượt (trên top-5):

  | Cấu hình | u01 | u02 |
  |---|---|---|
  | `dense` | 5, 0, 1, 0 | 5, 1, 0, 0 |
  | `bm25` | 5, 0, 2, 0 | 5, 1, 2, 1 |
  | `hybrid` | 5, 0, 0, 0 | 5, 2, 1, 0 |

  Lượt 3–4 hầu như không thêm chunk nào, và quyết định cuối vẫn là từ chối. Mỗi câu thiếu evidence tốn khoảng 2,7–3,2 lần chi phí của một câu có đáp án; 2 câu này chiếm 26–30% tổng chi phí dev. Ngoài ra `bm25` dùng 4 lượt cho q09 và 3 lượt cho q13 dù evidence đã có từ lượt 1; ở q13 model còn chép đáp án vào truy vấn ("…N = 6 identical layers").
- **Nguyên nhân.** Không có tín hiệu nào cho model biết lượt tìm mới không đem lại gì, nên model chỉ dừng khi hết lượt. Với `max_searches = 4`, câu thiếu evidence luôn tốn đủ 4 lượt.
- **Thay đổi: ứng viên `searches-2`** (gốc `dense`, chỉ đổi `max_searches` từ 4 xuống 2).
- **Giả thuyết.** Chi phí và thời gian của câu thiếu evidence giảm khoảng một nửa, từ chối đúng giữ 2/2. Câu có đáp án hầu như không bị ảnh hưởng: ở `dense` trước khi sửa, 13/15 câu xong sau 1 lượt và 2/15 sau 2 lượt. Rủi ro: câu nào cần lượt thứ 3 trở lên sẽ phải trả lời với ngữ cảnh ít hơn hoặc từ chối.
- **Kết quả sau:**
  - Chi phí trung bình của u01, u02 giảm từ $0.00188 (`dense`) xuống $0.00104 (−45%). Tổng chi phí dev từ $0.0140 xuống $0.0119 (−15%); p90 thời gian từ 5.32 s xuống 3.57 s, trung vị gần như không đổi (2.43 s so với 2.65 s).
  - Từ chối đúng 2/2, từ chối nhầm 0/15, Context Evidence 15/15, như `dense`. Ở u02, lượt thứ 2 thêm 3 chunk mới nhưng agent vẫn từ chối đúng.
  - Không câu có đáp án nào cần lượt thứ 3: 14/15 câu xong sau 1 lượt, 1 câu (q02) dùng 2 lượt.
  - Grounded (nhãn tác giả): 13 câu đạt 2, 2 câu đạt 1 (q02, q07), trung bình 1.87/2, bằng đúng `dense`. Hai câu đạt 1 là lỗi 3, không liên quan tới số lượt tìm.
  - Kết luận: giả thuyết đúng trên dev. Chất lượng không đổi, chi phí và p90 thời gian giảm. Được chọn theo quy tắc hòa (`results/selection.md`).

## Lỗi 5 (phát hiện sau khi sửa): câu trả lời đúng bị luật citation chuyển thành từ chối

- **Hiện tượng.** Ở lần chạy lại, `hybrid` q03 và q07 có câu trả lời đúng nhưng kết quả là `abstain`, nên từ chối nhầm của `hybrid` là 2/15. Trace ghi `invalid_citations`: model điền ID vào trường `citations` mà không viết `[chunk-id]` trong văn bản. Ví dụ q03: "Không. Theo quy định, "sự im lặng hoặc không phản hồi … không được coi là sự đồng ý" …", citations = `[nd13-heading-0023]`.
- **Nguyên nhân.** Đây là lỗi định dạng ngẫu nhiên của model. Luật kiểm tra citation (mục 2 của `selection_criteria.md`) chuyển mọi câu trả lời như vậy thành từ chối. Tần suất: 2/85 lượt sau khi sửa, 0/51 lượt trước khi sửa. Ở C3, q01 cũng gặp lỗi này trước khi sửa câu chữ prompt. Hai câu này rơi vào `hybrid` do ngẫu nhiên, không phải do phương pháp retrieval: ngữ cảnh của cả hai câu đều có evidence ở hạng 1.
- **Không sửa ở vòng này.** Luật citation đã công bố trước khi chạy và áp dụng như nhau cho mọi cấu hình. Đổi luật sau khi thấy nó làm `hybrid` thua là chỉnh theo kết quả. Câu bị chuyển thành từ chối vẫn chấm 0 theo `BENCHMARK.md`. Ghi vào giới hạn của báo cáo, kèm hướng sửa: khi citation không hợp lệ, trả lỗi cho model và cho thử lại một lần thay vì từ chối ngay.

## Vì sao không chọn ba ứng viên đã công bố

- **`rerank`**: Evidence Hit@3 của `hybrid` đã là 15/15. Rerank chỉ đổi thứ tự trong top-5, mà ở q02 và q07 evidence đã đứng hạng 1.
- **`query`** (multi-query / RAG fusion): câu chéo ngôn ngữ trong dev (q20) đã có evidence ở top-3 với query gốc. Thêm truy vấn làm tăng chi phí, trong khi lỗi 4 cho thấy truy vấn thêm không mang lại chunk mới.
- **`context`** (budget 4.000 token hoặc chunk lân cận): ngữ cảnh cuối của các câu trả lời đều dưới 2.000 token và chứa evidence. Phần bị bỏ ở lỗi 3 nằm trong chính chunk được trích, không nằm ở chunk lân cận.

Các ứng viên này không cải thiện được lỗi nào đọc thấy trên dev, nên thay bằng hai ứng viên nhắm đúng lỗi 3 và lỗi 4 (`selection_criteria.md`, mục "Thay đổi").
