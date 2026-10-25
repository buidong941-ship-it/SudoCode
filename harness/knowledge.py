"""Tra cứu chính sách cho agent — lớp mỏng trên `harness/rag.py` (tìm lai vector + BM25 trên chunk [XX-nn] của policy/).

Ba luật an toàn nằm ở `rag.py` và áp trước khi xếp hạng:
- tài liệu HẾT HIỆU LỰC chỉ dùng khi truyền `order_date` của một đơn tạo trước ngày bản mới có hiệu lực;
- tài liệu NỘI BỘ không bao giờ trả cho LLM sinh lời (trừ khi gọi với include_restricted=True cho mục đích kiểm thử);
- tài liệu nhiễu (nội quy nhân viên) bị loại.
Khi máy không có model embedding, `rag` tự lùi về BM25 nên harness vẫn chạy được (xem `RAG_MODE`).
"""
import time

from harness import rag

CHUNKS = rag.CHUNKS
spent_ms = 0.0


def search(query, k=3, include_restricted=False, order_date=None):
    global spent_ms
    t0 = time.perf_counter()
    try:
        return rag.search(query, k=k, include_restricted=include_restricted, order_date=order_date)
    finally:
        spent_ms += (time.perf_counter() - t0) * 1000
