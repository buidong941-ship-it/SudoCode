"""Cờ ablation 04/11: STRIP_QUESTIONS, GUARD_MODE, MEM_ABLATE (mặc định tắt = hành vi cũ).

- mặc định: strip tắt, guard enforce, mem_ablate rỗng; giá trị lạ → ValueError;
- _strip_open_questions bỏ câu hỏi mở, giữ phần còn lại, trả None nếu không còn gì;
- _mem_layers: profile bỏ fact về khách, episodic bỏ fact về phiên trước;
- Memory.current_facts: ttl → không fact nào hết hạn; supersede → giá trị ghi sớm nhất thắng;
  mặc định vẫn trả giá trị mới nhất và ẩn fact hết hạn.
"""
import os
import sys
import tempfile
from unittest.mock import patch

TMP = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(TMP, "abl.db").replace("\\", "/")
for k in ("STRIP_QUESTIONS", "GUARD_MODE", "MEM_ABLATE"):
    os.environ.pop(k, None)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import Settings, settings  # noqa: E402
from harness import agent  # noqa: E402
from harness.memory import Memory  # noqa: E402

FAILS = []


def ok(c, m):
    if not c:
        FAILS.append(m)
        print("FAIL:", m)


def raises(env):
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        Settings()
        return False
    except ValueError:
        return True
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def check_config():
    s = Settings()
    ok(s.strip_questions is False and s.guard_mode == "enforce" and s.mem_ablate == frozenset(), "mặc định phải tắt hết")
    d = s.describe()
    ok(d["strip_questions"] is False and d["guard_mode"] == "enforce" and d["mem_ablate"] == [], "describe() ghi 3 cờ")
    ok(raises({"GUARD_MODE": "off"}), "GUARD_MODE lạ phải báo lỗi")
    ok(raises({"MEM_ABLATE": "profile,brief"}), "MEM_ABLATE lạ phải báo lỗi")
    os.environ["MEM_ABLATE"] = " Profile , ttl "
    ok(Settings().mem_ablate == {"profile", "ttl"}, "MEM_ABLATE tách dấu phẩy, bỏ khoảng trắng, chữ thường")
    os.environ.pop("MEM_ABLATE")


def check_strip():
    txt = "Dạ máy AirPure X giá 4.890.000đ ạ. Nhà mình phòng bao nhiêu mét vuông ạ?"
    out = agent._strip_open_questions(txt, {})
    ok(out == "Dạ máy AirPure X giá 4.890.000đ ạ.", f"cắt câu hỏi mở, được {out!r}")
    ok(agent._strip_open_questions("Anh cần gì ạ?", {}) is None, "chỉ có câu hỏi → None")
    keep = "Dạ em gửi giá ạ. Anh vẫn lấy size L đúng không ạ?"
    ok(agent._strip_open_questions(keep, {"size": "L"}) == keep, "câu xác nhận không bị cắt")


def check_layers():
    f = {"budget_vnd": {"value": 5_000_000}, "product_advised": {"value": "SKU-1"}, "price_quoted_vnd": {"value": 1}}
    ok(agent._mem_layers(f) == f, "mặc định không lọc")
    with patch.object(settings, "mem_ablate", frozenset({"profile"})):
        ok(set(agent._mem_layers(f)) == {"product_advised", "price_quoted_vnd"}, "profile: chỉ còn slot episodic")
    with patch.object(settings, "mem_ablate", frozenset({"episodic"})):
        ok(set(agent._mem_layers(f)) == {"budget_vnd"}, "episodic: bỏ slot về phiên trước")


def check_memory():
    m = Memory("abl:test")
    m.wipe()
    m.write_fact("C1", "color", "đỏ", "s1", "s1", "2026-10-01")
    m.write_fact("C1", "color", "trắng", "s2", "s2", "2026-10-03")
    m.write_fact("C1", "price_quoted_vnd", 4_890_000, "s1", "s1", "2026-08-01")      # TTL 30 ngày → hết hạn 31/8
    cur = m.current_facts("C1", "2026-10-15")
    ok(cur["color"]["value"] == "trắng", "mặc định: giá trị mới nhất")
    ok("price_quoted_vnd" not in cur, "mặc định: fact hết hạn bị ẩn")
    with patch.object(settings, "mem_ablate", frozenset({"supersede"})):
        ok(m.current_facts("C1", "2026-10-15")["color"]["value"] == "đỏ", "supersede: giá trị cũ thắng")
    with patch.object(settings, "mem_ablate", frozenset({"ttl"})):
        got = m.current_facts("C1", "2026-10-15")
        ok("price_quoted_vnd" in got and not got["price_quoted_vnd"]["expired"], "ttl: không fact nào hết hạn")
    m.wipe()


def main():
    check_config()
    check_strip()
    check_layers()
    check_memory()
    print("ablation_flags_check:", "OK" if not FAILS else f"{len(FAILS)} lỗi")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
