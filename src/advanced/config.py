"""Đường dẫn và hằng số của phần nâng cao. Import `src.lab_config` trước (biến môi trường, Perrier)."""

from src import lab_config as C

DOC_ID = "dlcb"
SOURCE = "Deep Learning cơ bản (Nguyễn Thanh Tuấn, v2, 2020)"
PDF_SHA256 = "4889d114864702d415a73a25bb8d4955535a6a4694e6d508ec4b0d3082c2a5ca"
PAGES = 301

ROOT = C.DATA / "advanced"
PDF = ROOT / "raw" / "deep-learning-co-ban-v2.pdf"
PARSED = ROOT / "parsed"
PAGES_FILE = PARSED / "pages.jsonl"
DESCRIPTIONS = PARSED / "figure_descriptions.jsonl"
FIGURES = ROOT / "figures"  # ảnh crop, đường dẫn tương đối từ gốc repo ghi trong chunk
CHUNKS = ROOT / "chunks.json"
QUESTIONS = ROOT / "questions.json"
RESULTS = C.RESULTS / "advanced"

# Bảng pgvector riêng, không đụng `lab_chunks` của phần cơ bản.
TABLE = "adv_chunks"
CHUNKING = "adv"

# Ghép lại dấu cách: khoảng hở giữa hai glyph lớn hơn RATIO × chiều cao glyph là một dấu cách.
# Quét cả 301 trang: từ 0,10 đến 0,18 cho cùng kết quả; token dính 2 dấu thanh từ 2 670 về 0.
SPACE_RATIO = 0.15
# Dòng đầu trang (tên mục + số trang) nằm trên y = 80.
HEADER_BOTTOM = 80
# Chương 1 (trang 19-32) là ảnh chụp màn hình cài đặt: chỉ index caption, không mô tả.
SCREENSHOT_PAGES = range(19, 33)
# Ảnh crop JPEG: PNG 150 dpi nặng 48 MB cho 221 hình, quá lớn để commit.
CROP_DPI = 120
CROP_QUALITY = 80
