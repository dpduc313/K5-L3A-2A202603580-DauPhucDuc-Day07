# Tài liệu phần nâng cao

## Nguồn

| | |
|---|---|
| Tài liệu | *Deep Learning cơ bản*, Nguyễn Thanh Tuấn |
| Phiên bản | v2 (tháng 8/2020; PDF tạo bằng pdfTeX ngày 2020-08-07) |
| Số trang | 301 |
| File | `raw/deep-learning-co-ban-v2.pdf`, 36 923 441 byte |
| sha256 | `4889d114864702d415a73a25bb8d4955535a6a4694e6d508ec4b0d3082c2a5ca` |
| Bản quyền | "Copyright © 2019 Nguyễn Thanh Tuấn"; sách được tác giả chia sẻ miễn phí |
| Quyền sử dụng | Tác giả đã cho phép dùng và commit bản PDF vào repo này (theo xác nhận của người làm bài, 2026-11-15). Mọi nội dung thuộc về tác giả. |
| Truy cập bản gốc | Trang giới thiệu sách `nttuan8.com/sach-deep-learning-co-ban/` trả 404 (2026-11-15); code đi kèm sách ở GitHub `nttuan8/DL_Tutorial`. Bản dùng để chấm là file PDF trong repo, kiểm tra bằng sha256 ở trên. |

Sách có text, 14 bảng có kẻ ô, 221 hình có caption (biểu đồ, sơ đồ, ảnh minh họa, ảnh chụp màn hình) và 54 ảnh không caption có thông tin.

## Cách xử lý

Chạy lại từ gốc repo, theo thứ tự:

```
uv run python -m src.advanced.extract     # PDF -> parsed/pages.jsonl, figures/*.jpg
uv run python -m src.advanced.describe    # mô tả hình bằng gpt-5.4-mini (tốn phí, có cache)
uv run python -m src.advanced.chunks      # -> chunks.json
uv run python -m src.advanced.index       # -> bảng pgvector adv_chunks
uv run python -m src.advanced.benchmark   # kiểm tra questions.json
```

| Phần | Cách làm | Kiểm tra |
|---|---|---|
| Text | Lớp text của PDF, nhưng ghép lại dấu cách từ vị trí glyph (`rawdict`): khoảng hở > 0,15 × chiều cao glyph là dấu cách. `get_text()` mặc định làm dính chữ sau dấu ("Đồthịquan"). | Token có ≥ 2 dấu thanh (một âm tiết tiếng Việt chỉ có một): 2 670 token ở 254 trang với `get_text()` mặc định, 0 sau khi ghép lại. Token ≥ 16 chữ cái còn lại đều là tên hàm/URL thật (`BatchNormalization`, `towardsdatascience`). |
| Bảng | `find_tables` của PyMuPDF (bảng có kẻ ô), chữ trong ô cũng ghép theo glyph, lưu Markdown. Bỏ "bảng" có ô dài hơn 40 ký tự (trang 4: câu văn tô nền bị nhận nhầm). | 14 bảng, đối chiếu từng bảng với trang gốc. |
| Hình | Caption "Hình N.M:" nhận các ảnh raster ngay phía trên nó (không có đoạn văn ở giữa). Ảnh không caption thành hình riêng `img-pNNN-k`. Crop vùng hình + caption, JPEG 120 dpi. | `results/advanced/extraction_report.json`: 0 caption không tìm được vùng; khối text bị ẩn trong vùng hình/bảng chỉ còn chữ trong ô bảng. |
| Mô tả hình | `gpt-5.4-mini` mô tả mỗi hình một lần (loại hình, trục, chú giải, chữ và số đọc được) để hình tìm được bằng truy vấn chữ. Mô tả được đánh dấu là tự động trong chunk. | Agent không dựa vào mô tả khi trả lời: tool `view_figure` gửi chính ảnh crop cho model. |
| Chunk | Theo mục lục PDF (có tọa độ đích nên biết mục bắt đầu ở dòng nào); text gộp tới 350 token, không vượt ranh giới mục; mỗi bảng và mỗi hình là một chunk riêng. | 661 chunk: 372 text, 14 bảng, 275 hình. Mỗi chunk có `page`, `pages`, `locator` (trang + vùng bbox, đơn vị pt, gốc trên-trái); chunk hình có đường dẫn ảnh crop. |
| Index | `embeddinggemma-2` qua Ollama, bảng pgvector `adv_chunks` riêng (không đụng `lab_chunks` của phần cơ bản), cosine exact. | `results/advanced/index_log.jsonl`; chạy lại lần hai: 0 chunk embed lại. |

## Phần không xử lý

| Phần | Lý do | Ảnh hưởng |
|---|---|---|
| Trang 1 (bìa), 23 banner đầu chương (ảnh rộng hết trang, sát mép trên) | Ảnh trang trí, không có thông tin. | Không có. |
| 18 ảnh chụp màn hình cài đặt ở chương 1 (trang 19–32) không caption; 9 hình có caption trong chương 1 chỉ index caption, không mô tả | Ảnh chụp màn hình giao diện cài đặt Anaconda/Colab. | Câu hỏi về chi tiết giao diện cài đặt không trả lời được. |
| 18 trang không có chunk: 1, 18, 32, 44, 46, 82, 96, 108, 122, 138, 148, 158, 160, 176, 192, 204, 226, 264 | Trang trắng, trang tên Phần, bìa. | Không có. |
| Công thức toán | Lớp text của LaTeX: chỉ số trên/dưới bị tách dòng (`x[1]` / `j`), ký hiệu như `∂`, `σ` giữ nguyên. | Câu hỏi đọc công thức phức tạp có thể sai; benchmark không hỏi chi tiết công thức trong text. |
| Bảng dạng ảnh (vd. Hình 7.16, 19.10) | Không có lớp text: xử lý như hình (mô tả + `view_figure`). | Phụ thuộc chất lượng vision model. |
