"""Allowlist dữ liệu gửi cho model (ủy quyền theo cụm 10/11, cụm 1).

Một chỗ chung cho generator / summarizer / selector: bỏ đệ quy (kể cả trong dict/list lồng nhau)
  - field nội bộ của tool (tên bắt đầu bằng "_", vd `_internal_price_floor_vnd` — giá sàn không được lộ cho khách);
  - field định danh / quyền không cần để nói chuyện (customer_id, identities, zalo_id, fb_id, candidates, session_id…);
  - khóa ngoài allowlist cấp cao nhất của từng bên nhận (khi có allowlist).
Trả về bản sao đã lọc và danh sách đường dẫn đã bỏ (để ghi trace, không ghi giá trị).
Không thay việc che PII khi gọi model bên ngoài (core.pii.Redactor) — hai lớp độc lập.
"""

IDENTITY_KEYS = frozenset({"customer_id", "identities", "zalo_id", "fb_id", "channel_identity", "candidates", "session_id",
                           "run_id", "merged_from", "crm_id"})

# Khóa cấp cao nhất generator được nhận (plan dựng trong CallSession.turn + improve_hook + GOAL_NOTES/PLACEHOLDERS của payload)
GENERATOR_TOP = frozenset({"honorific", "customer_name", "call", "is_returning", "customer_said", "intent", "goals", "facts",
                           "KNOWN", "question_slot", "PLAYBOOK", "EXEMPLARS", "GOAL_NOTES", "PLACEHOLDERS", "STYLE"})


def scrub(obj, top=None, path=""):
    """→ (bản sao đã lọc, [đường dẫn đã bỏ])."""
    dropped = []

    def walk(x, p, level):
        if isinstance(x, dict):
            out = {}
            for k, v in x.items():
                key = str(k)
                q = f"{p}.{key}" if p else key
                if key.startswith("_") or key in IDENTITY_KEYS or (level == 0 and top is not None and key not in top):
                    dropped.append(q)
                    continue
                out[k] = walk(v, q, level + 1)
            return out
        if isinstance(x, list):
            return [walk(v, f"{p}[{i}]", level + 1) for i, v in enumerate(x)]
        return x

    return walk(obj, path, 0), dropped
