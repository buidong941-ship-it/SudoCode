"""18/11 candidate: sửa hướng dẫn điều phối thành PHIÊN BẢN MỚI (không sửa tại chỗ) + duyệt có thay thế bản cũ.

Nguyên tắc (lời giao 17/11 tối): nút "Chỉnh sửa" cho từng bản nháp; lưu thành phiên bản nháp mới rồi chạy lại test và duyệt;
KHÔNG sửa trực tiếp phiên bản đã đóng gói hoặc đang kích hoạt.

- `revise(pid, changes, by, note)`: bản gốc ở pending/ hoặc approved/ → đề xuất MỚI ở pending/ (payload.version + 1, cùng guide_id,
  id mới theo nội dung, `revision_of` = id cũ, giữ tests / nguồn / phân loại). Bản gốc KHÔNG bị ghi đè:
    * gốc ở pending/  → chuyển sang rejected/ với lý do "thay bằng <id mới>" (sự kiện supersede), để không còn hai bản chờ duyệt;
    * gốc ở approved/ → GIỮ NGUYÊN ở approved/ cho tới khi bản mới được duyệt (gói đã đóng là bản sao bất biến, gói đang kích hoạt
      không đổi; phải đóng gói + kích hoạt lại mới có hiệu lực).
  Nội dung mới phải qua đúng `store.validate` như lúc nhập; lỗi → không lưu gì.
- `approve(pid, by, reason)`: duyệt như `store.approve`, rồi mọi bản ĐÃ DUYỆT khác cùng guide_id chuyển sang rejected/ (supersede) —
  một guide_id chỉ có một bản trong approved/. Gói đã đóng trước đó không bị chạm.
- `approved_duplicates()`: guide_id có > 1 bản đã duyệt (đóng gói từ chối khi có).
Mọi thay đổi ghi log.jsonl của kho (revise / supersede). Module này chỉ dùng improve.store — không import harness / ui.
"""
from improve import store as S

EDIT_FIELDS = ("title", "audience", "tags", "applies_when", "exceptions", "guidance", "avoid", "examples", "counterexamples",
               "requires_capabilities", "conflict_group", "asks_any")
LIST_FIELDS = ("tags", "applies_when", "exceptions", "guidance", "avoid", "examples", "counterexamples", "requires_capabilities",
               "asks_any")
REQUIRED = ("title", "audience", "applies_when", "guidance", "examples")


def _clean(field, v):
    if field in LIST_FIELDS:
        return [str(x).strip() for x in (v or []) if str(x).strip()]
    return (str(v).strip() if v is not None else "") or None


def _content(pl):
    return {k: _clean(k, pl.get(k)) for k in EDIT_FIELDS}


def versions(guide_id, root=None):
    """Mọi bản (mọi trạng thái) của một guide_id → [(state, prop)]."""
    out = []
    for st in S.STATES:
        for p in S.list_state(st, root):
            if p.get("kind") == "planner_guidance" and guide_id and p["payload"].get("guide_id") == guide_id:
                out.append((st, p))
    return out


def revise(pid, changes, by, note, root=None):
    """→ id đề xuất mới (pending). Lỗi (không tên / không lý do / không thay đổi / không hợp lệ / sai trạng thái) → ProposalError."""
    if not (by or "").strip():
        raise S.ProposalError("phải ghi người sửa")
    if not (note or "").strip():
        raise S.ProposalError("phải ghi lý do sửa")
    state, old = S.find(pid, root)
    if old.get("kind") != "planner_guidance":
        raise S.ProposalError(f"{pid} không phải hướng dẫn điều phối")
    if state not in ("pending", "approved"):
        raise S.ProposalError(f"chỉ sửa bản chờ duyệt hoặc đã duyệt (đang {state})")
    bad = set(changes or {}) - set(EDIT_FIELDS)
    if bad:
        raise S.ProposalError(f"trường không được sửa: {sorted(bad)}")
    pl = dict(old["payload"])
    for k, v in (changes or {}).items():
        v = _clean(k, v)
        if v in (None, []) and k not in REQUIRED:
            pl.pop(k, None)                       # trường tùy chọn để trống → bỏ
        else:
            pl[k] = v                             # trường bắt buộc để trống → validate báo lỗi, không lưu
    if _content(pl) == _content(old["payload"]):
        raise S.ProposalError("không có thay đổi nội dung")
    gid = pl.get("guide_id")
    pl["version"] = max([int(p["payload"].get("version") or 1) for _, p in versions(gid, root)] + [int(old["payload"].get("version") or 1)]) + 1
    new = {"kind": "planner_guidance", "payload": pl, "source_gaps": list(old.get("source_gaps") or []), "title": pl.get("title"),
           "tests": list(old.get("tests") or []), "classification": old.get("classification"), "revision_of": pid,
           "revision_note": note.strip(), "author": by.strip()}
    errs = S.validate(new)
    if errs:
        raise S.ProposalError("bản sửa không hợp lệ: " + "; ".join(errs))
    st, nid = S.propose(new, author=by.strip(), root=root)
    if st != "pending":
        raise S.ProposalError(f"nội dung trùng đề xuất đã có {nid} ({st})")
    if state == "pending":
        S._move(pid, "rejected", by, f"thay bằng {nid} (v{pl['version']}): {note.strip()}", root, event="supersede")
    S.log("revise", root, id=nid, revision_of=pid, from_state=state, version=pl["version"], by=by.strip(), note=note.strip())
    return nid


def approve(pid, by, reason="", root=None):
    """Duyệt + thay thế bản đã duyệt cũ cùng guide_id. → (prop đã duyệt, [id bị thay])."""
    prop = S.approve(pid, by, reason, root=root)
    sup = []
    gid = prop["payload"].get("guide_id") if prop.get("kind") == "planner_guidance" else None
    if gid:
        for p in S.list_state("approved", root):
            if p["id"] != pid and p.get("kind") == "planner_guidance" and p["payload"].get("guide_id") == gid:
                S._move(p["id"], "rejected", by, f"thay bằng {pid} (v{prop['payload'].get('version')}) khi duyệt", root, event="supersede")
                sup.append(p["id"])
    return prop, sup


def approved_duplicates(root=None):
    seen = {}
    for p in S.list_state("approved", root):
        if p.get("kind") == "planner_guidance":
            seen.setdefault(p["payload"].get("guide_id"), []).append(p["id"])
    return {g: ids for g, ids in seen.items() if g and len(ids) > 1}
