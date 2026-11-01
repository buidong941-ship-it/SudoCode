"""Đọc bộ approved/ cho agent — điểm nối DUY NHẤT giữa cơ chế cải tiến và core (mục E bật, sau cờ mặc định tắt).

Chỉ đọc approved/: pending/ và rejected/ không bao giờ tới được agent. Mỗi đề xuất được kiểm lại bằng
`store.validate` khi nạp, nên một file bị sửa tay sau khi duyệt mà vi phạm luật (vd thêm số tiền) sẽ bị bỏ qua.
"""
from improve import store


def load_approved(root=None):
    """→ {"items": {kind: [payload + id]}, "hash": str, "skipped": [(id, lỗi)]}"""
    items, skipped = {k: [] for k in store.KINDS}, []
    for prop in store.list_state("approved", root):
        errs = store.validate(prop)
        if errs:
            skipped.append((prop.get("id"), errs))
            continue
        items[prop["kind"]].append({"id": prop["id"], **prop["payload"]})
    return {"items": items, "hash": store.approved_hash(root), "skipped": skipped}
