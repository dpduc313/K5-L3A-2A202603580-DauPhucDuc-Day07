# Cấu hình được chọn trên dev

Chọn **`searches-2`**: agent `dense` với tối đa 2 lượt search. File này được commit **trước** lần chạy test đầu tiên; runner từ chối split `test` cho tới khi file này đã được commit (`src/experiment.py: guard_test_split`).

## Căn cứ

- Tiêu chí và thứ tự chọn: `results/selection_criteria.md` mục 4, cùng mục "Thay đổi" (ứng viên mới; cách hiểu quy tắc hòa với grounded).
- Trace: `results/agent/<cấu hình>/dev/`, chạy trên commit `115daa3`, `gpt-5.4-nano`, `dirty: false`.
- Retrieval không qua agent: `results/retrieval/<phương pháp>/dev/`.
- Nhãn tay: `results/labels/{answers,citations}.csv`, tổng hợp ở `results/labels/summary_dev.json`. Tác giả đã duyệt cả 166 dòng và giữ nguyên toàn bộ nhãn gợi ý (0 dòng sửa).
- Lỗi và giả thuyết: `results/dev_errors.md`.

## Bảng dev

15 câu có đáp án, 2 câu thiếu evidence. Grounded là tổng điểm /30 kèm trung bình /2.

| Cấu hình | Vai trò | Hit@1 | Hit@3 | Context Evidence | Grounded | Từ chối đúng | Từ chối nhầm | Hành vi từ chối (/17) | Citation hợp lệ | Chi phí/câu | Trung vị | p90 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dense` | baseline | 10/15 | 15/15 | 15/15 | 28 (1.87) | 2/2 | 0/15 | 17 | 16/16 | $0.000822 | 2.65 s | 5.32 s |
| `bm25` | phương pháp 2 | 12/15 | 14/15 | 15/15 | **30 (2.00)** | 2/2 | 0/15 | 17 | 17/17 | $0.001014 | 2.33 s | 4.80 s |
| `hybrid` | phương pháp 3 | 11/15 | 15/15 | 15/15 | 25 (1.67) | 2/2 | 2/15 | 15 | 14/14 | $0.000940 | 2.33 s | 5.16 s |
| `answer-rules` | cải thiện 1 (gốc dense) | 10/15 | 15/15 | 15/15 | 29 (1.93) | 2/2 | 0/15 | 17 | 17/17 | $0.001044 | 2.35 s | 5.57 s |
| `searches-2` | cải thiện 2 (gốc dense) | 10/15 | 15/15 | 15/15 | 28 (1.87) | 2/2 | 0/15 | 17 | 17/17 | **$0.000702** | 2.43 s | 3.57 s |

Ghi chú bảng:
- Hit@1/Hit@3 của hai ứng viên bằng của `dense`, vì cả hai không đổi retrieval.
- "Hành vi từ chối" = số câu thiếu evidence được từ chối + số câu có đáp án không bị từ chối nhầm.
- Không có lỗi model hay vector store ở cấu hình nào.

## Áp dụng thứ tự chọn

1. **Context Evidence**: cả 5 cấu hình 15/15, hòa.
2. **Grounded**: `bm25` cao nhất (30). Vì `bm25` không kém ở tiêu chí 3, **X = `bm25`**.
3. **Quy tắc hòa**: Y phải rẻ hơn X ($0.001014/câu) và kém X không quá 1 câu ở tiêu chí 1 và 3, không quá 2 điểm grounded ở tiêu chí 2.

| Y | Rẻ hơn X? | Tiêu chí 1 | Tiêu chí 2 | Tiêu chí 3 | Ngang X? |
|---|---|---|---|---|---|
| `dense` | có ($0.000822) | 0 | −2 điểm | 0 | **có** |
| `searches-2` | có ($0.000702) | 0 | −2 điểm | 0 | **có** |
| `hybrid` | có ($0.000940) | 0 | −5 điểm | −2 câu | không |
| `answer-rules` | không ($0.001044) | | | | không xét |

4. Trong các cấu hình ngang X (`bm25`, `dense`, `searches-2`), chọn cấu hình rẻ nhất: **`searches-2`**.

## Vì sao kết quả này hợp lý

- Hai điểm `bm25` hơn `dense` đến từ q02 và q07. Cả hai là lỗi bỏ vế điều kiện ở bước viết câu trả lời (lỗi 3), không phải lỗi retrieval: ở `dense`, evidence của hai câu đứng hạng 1 trong ngữ cảnh. Ở lần chạy trước khi sửa, `bm25` cũng bỏ vế cha mẹ ở q02. Vì vậy phần hơn của `bm25` có khả năng là nhiễu giữa các lần chạy.
- `searches-2` giữ nguyên chất lượng của `dense` trên mọi tiêu chí, nhưng rẻ hơn 15% và có p90 thấp hơn 1,75 s, vì câu thiếu evidence không còn tốn 4 lượt.

## Giới hạn đã biết khi chốt

- Dev có 15 câu có đáp án. Mỗi cấu hình chỉ chạy một lần, nên chênh 1–2 câu nằm trong vùng nhiễu.
- `searches-2` chưa được thử với câu cần từ 3 lượt tìm trở lên; dev không có câu như vậy.
- Lỗi 3 (bỏ vế điều kiện ở q02) và lỗi 5 (luật citation chuyển câu trả lời đúng thành từ chối) vẫn có thể xảy ra ở test.

## Kế hoạch test

- Chạy **một lần** trên split `test` (5 câu có đáp án, 2 câu thiếu evidence u03, u04): `dense` (baseline) và `searches-2` (được chọn). Cùng model, cùng commit code.
- Chạy thêm retrieval không qua agent của `dense` trên test (`searches-2` dùng cùng retrieval).
- Chấm tay: grounded, citation, abstention cho cả hai cấu hình; context 0/1/2 cho 5 câu có đáp án (`BENCHMARK.md` mục 2).
- Không sửa hệ thống theo kết quả test. Nếu phải sửa thì cần bộ test mới.
