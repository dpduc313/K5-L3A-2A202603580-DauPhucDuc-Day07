"""Cấu hình chung của lab: đường dẫn, biến môi trường và cách nạp Perrier.

Chép từ Lab06 (src/lab_config.py, bản local trên 646216f) và sửa cho Lab07.

Lab dùng bản sao đầy đủ của Perrier nằm trong repo (src/perrier, commit dd09dad của
https://github.com/dpduc313/perrier) cho phần đọc tài liệu (Docling, vision reader),
chunking (heading/fixed), embedding (EmbeddingGemma 2 qua Ollama) và chat model. Không
đọc Perrier ở đâu khác ngoài repo. Perrier đọc biến môi trường lúc import, nên module
này phải được import TRƯỚC mọi `import perry`.
"""

import os
import sys
import unicodedata
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Postgres + pgvector riêng của Lab07 (compose.yaml, port 55434), không dùng DB của Day 6.
os.environ.setdefault(
    "DATABASE_URL", "postgresql://day7:day7_local_only@127.0.0.1:55434/day7_lab"
)
DATABASE_URL = os.environ["DATABASE_URL"]

# Tắt reranker mặc định của Perrier (ms-marco-MiniLM, chỉ tiếng Anh) cho mọi lệnh của lab:
# ở Day 6 nó làm Evidence Hit@5 tụt từ 20/20 xuống 17/20. Cấu hình có rerank chọn model
# trong code thí nghiệm. " " chứ không phải "": trên Windows, gán chuỗi rỗng (kể cả qua
# .env) sẽ xóa biến môi trường và Perrier quay về reranker mặc định.
if not os.environ.get("PERRY_RERANK_MODEL", "").strip():
    os.environ["PERRY_RERANK_MODEL"] = " "

PERRIER_DIR = ROOT / "src" / "perrier"
if not (PERRIER_DIR / "perry" / "__init__.py").exists():
    sys.exit(f"Không tìm thấy bản sao Perrier ở {PERRIER_DIR}.")
sys.path.insert(0, str(PERRIER_DIR))

DATA = ROOT / "data"
RAW = DATA / "raw"  # PDF gốc không commit; tải theo hướng dẫn trong README nếu cần parse lại
OCR_CACHE = DATA / "ocr"
PARSED = DATA / "parsed"
QUESTIONS = DATA / "questions.json"
CHUNKS = DATA / "chunks.json"
RESULTS = ROOT / "results"
LABELS = RESULTS / "labels"

# Bản index dùng cho Day 7: chunk theo heading (chiến lược B, đã chọn ở Day 6).
CHUNKING = "heading"
# Fingerprint bản parse Day 6 đã duyệt (Lab06 results/index_log.jsonl); data/parsed chép nguyên.
DAY6_APPROVED_FINGERPRINT = "e6054dd139ec"

# Tài liệu trong corpus và các trang được tính (xem data/manifest.json).
DOCUMENTS = {
    "aiayn": {
        "file": "aiayn.pdf",
        "reader": "docling",
        "language": "en",
        "document_type": "paper",
        # Trang 11-12 là tài liệu tham khảo, 13-15 là hình minh họa attention: không tính.
        "pages": list(range(1, 11)),
    },
    "nd13": {
        "file": "nd13.pdf",
        "reader": "vision",  # bản scan: không có lớp text
        "language": "vi",
        "document_type": "decree",
        # Trang 29-39 là Phụ lục biểu mẫu (chủ yếu ô trống, dòng chấm): không tính.
        "pages": list(range(1, 29)),
    },
}

def normalize(text: str) -> str:
    """Chuẩn hóa dùng chung cho chunk, trang và evidence: NFC, nối từ bị gạch nối cuối
    dòng, bỏ định dạng Markdown nhấn mạnh, gộp khoảng trắng, chữ thường."""
    text = unicodedata.normalize("NFC", text)
    # Docling xuất Markdown có escape (`warmup\_steps`), còn text chunk thì không.
    text = re.sub(r"\\([_*#\[\]()<>`|\\])", r"\1", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[*_`#|]+", " ", text)
    return " ".join(text.split()).casefold()
