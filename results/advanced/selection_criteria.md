# Tiêu chí chọn cấu hình — phần nâng cao

Ghi trước lần chạy dev đầu tiên và commit trước khi chạy. Benchmark: `data/advanced/questions.json`
(dev 24 câu, test 30 câu), tác giả đã đối chiếu từng câu với bản gốc trước khi chạy
(`results/advanced/benchmark_review.json`). Tác giả duyệt các tiêu chí này ngày 2026-11-15, gồm
cách chấm dev: chỉ gán nhãn cho 2 cấu hình đứng đầu theo metric tự động.

## 1. Cấu hình

Mọi cấu hình dùng chung: index `adv_chunks` (661 chunk), `gpt-5.4-nano` với `reasoning_effort = none`,
top-k 5, budget ngữ cảnh 2 000 token, tối đa 4 lượt tìm và 2 lượt `view_figure`, và 3 quy tắc riêng của
phần nâng cao (`ADV_RULES` trong `src/advanced/experiment.py`: xem ảnh trước khi trả lời câu về hình,
được làm phép tính đơn giản, trích đủ nguồn cho câu nhiều phần).

| Cấu hình | Vai trò | Khác `dense` ở |
|---|---|---|
| `dense` | baseline | |
| `bm25` | phương pháp 2 | retrieval BM25 |
| `hybrid` | phương pháp 3 | retrieval RRF dense + BM25 |
| `no-view` | đối chứng | không có tool `view_figure` (chỉ dựa vào mô tả tự động) |

Vòng 2 (sau khi xem kết quả vòng 1 trên dev): một cấu hình chỉ đổi model sang `gpt-5.4-mini` trên cấu
hình tốt nhất vòng 1, và tối đa một cấu hình sửa lỗi rút ra từ dev. Mỗi cấu hình mới chỉ đổi một yếu tố,
ghi vào mục "Thay đổi" bên dưới trước khi chạy.

## 2. Metric trên dev

1. **Đạt tự động** (`auto_pass`, `src/advanced/metrics.py`): câu có đáp án đạt khi agent trả lời và
   trích đủ mọi chunk evidence; câu thiếu evidence đạt khi agent từ chối. Lỗi hệ thống tính không đạt.
   Đây chỉ là chỉ báo: không kiểm tra nội dung câu trả lời.
2. **Đạt theo nhãn**: Mr Duke gợi ý nhãn đạt/không đạt cho từng câu dev của 2 cấu hình đứng đầu theo
   (1), theo đúng cách chấm test ở ADVANCED.md mục 3 (đúng và đủ, đúng đơn vị/điều kiện/phép tính,
   citation đúng chỗ); tác giả duyệt.
3. Phụ: lỗi hệ thống, chi phí, thời gian trung vị.

## 3. Quy tắc chọn

- Chọn cấu hình có số câu **đạt theo nhãn** (2) cao nhất.
- Hòa (chênh không quá 1 câu): chọn cấu hình ít lỗi hệ thống hơn, rồi rẻ hơn.
- `gpt-5.4-mini` chỉ được chọn nếu đạt nhiều hơn cấu hình nano tốt nhất ít nhất 2 câu (đắt hơn khoảng 4 lần).
- Chốt cấu hình trong `results/advanced/selection.md` và commit trước khi chạy test. Test chạy đúng
  một lần với cấu hình đã chốt; nếu sau đó sửa pipeline vì test thì phải tạo test mới trước khi báo điểm.

## 4. Ngân sách API

Tổng $1 cho phần nâng cao. Đã dùng $0,353 cho mô tả hình. Dừng và hỏi tác giả trước khi vượt $1.

## Thay đổi

(trống)
