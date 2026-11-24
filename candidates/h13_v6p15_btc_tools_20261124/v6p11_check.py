"""Kaggle only. v6p11 (ADDRESS_SCOPE_GATE): phạm vi địa chỉ + lời kể trạng thái đơn — DeepSeek trích kèm căn cứ, JEV phân loại kiểm
chéo, code giữ hàng rào ghi đơn và ghi hồ sơ; tắt cờ = v6p10 ở prompt / schema / câu hỏi JEV."""
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
frame_path = ROOT / "tests/b2_round_f_check.py"
F = types.ModuleType("v6p11_frame")
F.__file__ = str(frame_path)
exec(compile(frame_path.read_text(encoding="utf-8").split("# ================================================================== H8")[0],
             str(frame_path), "exec"), F.__dict__)
from harness import jev_write_gate as G
from harness import understanding as U

passed, failed = 0, []


def check(name, value):
    global passed
    if value:
        passed += 1
        print("PASS", name, flush=True)
    else:
        failed.append(name)
        print("FAIL", name, flush=True)


JEV = {"scope": "profile_default", "claim": "none"}
SEEN = {}


def decision(state, opts):
    SEEN["opts"] = sorted(opts)
    action = state["proposed_update"]["action"]
    out = {"decision": "reject_or_withdraw" if action == "withdraw" else "open_or_update_request",
           "request_id": opts["request_ids"][0], "target_ref": opts["target_refs"][0], "revision": opts["revision"]}
    if "address_scope" in opts:
        SEEN["proposed_keys"] = sorted(state["proposed_update"])
        out.update(address_scope=JEV["scope"], order_state_claim=JEV["claim"])
    return out


real_assess = G.assess


def assess(*args, **kwargs):
    return real_assess(*args, **kwargs, decider=decision)


def planner(state, opts):
    steps = opts["step"]
    for req_ in state.get("open_requests") or []:
        for detail in req_.get("readiness", {}).get("detail") or []:
            if detail in steps:
                return {"step": detail}
    for prefix in ("commit_request:", "answer_ask:", "clarify:", "read_order", "read_quote:", "read_stock:", "check_window:",
                   "clarify", "finish"):
        found = next((x for x in steps if x.startswith(prefix)), None)
        if found:
            return {"step": found}
    return {"step": "finish"}


SENTINEL = F.resp(intent="greeting_or_other")


def turn(s, text, *resps):
    F.QUEUE[:] = list(resps)
    row = s.turn(text)
    s.drain_audits()
    return row


def req(kind, evidence, ref=None, **kw):
    return {"kind": kind, "evidence": evidence, "target_ref": ref, **kw}


def addr_obs(span):
    return [{"slot": "address", "span": span, "stance": "stated", "subject": "self"}]


def mem_addr(row):
    return [w for w in row.get("memory_writes") or [] if w.get("key") == "address"]


def prior_order(s):
    """Đơn từ cuộc gọi TRƯỚC, đã có địa chỉ (như H13-057): tạo qua tool, không nằm trong orders_created của cuộc này."""
    q = s.tools.call("pricing.quote_order", lines=[{"sku": "SKU-AP-MINI", "qty": 1}], customer_phone=s.phone)
    o = s.tools.call("order.create", customer_phone=s.phone, payment="COD", address="140 Nguyễn Thị Thập, Quận 7, TP HCM",
                     lines=[{"sku": u["sku"], "qty": 1, "price_vnd": u["final_price_vnd"]} for u in q["units"]])
    return o.get("order_id")


def debug(label, row):
    rs = row.get("request_state") or {}
    ev = [(e.get("event"), e.get("why") or e.get("kind")) for e in rs.get("events") or []][-8:]
    steps = [d.get("step") for d in ((row.get("planner") or {}).get("loop") or {}).get("decisions") or []]
    print(f"  [{label}] events {ev} | steps {steps} | why {str(row.get('why') or row.get('decision_log') or '')[:200]}", flush=True)


def ordered(s):
    turn(s, "Lấy AirPure Mini cho chị", F.resp(intent="place_order", requests=[req("place_order", "Lấy AirPure Mini", "P1",
         target_basis="named")]), SENTINEL)
    return s.orders_created[0]["order_id"] if s.orders_created else None


NEW = "92 Trần Phú, Nha Trang, Khánh Hòa"
T_PROFILE = f"Chị dọn nhà rồi, địa chỉ mới là {NEW}, mấy đơn sau gửi về đây nha"


def profile_turn(s, scope="profile_default", span="mấy đơn sau gửi về đây", claim="none", **kw):
    return turn(s, T_PROFILE, F.resp(intent="order_change", requests=[req("change_order_address", f"địa chỉ mới là {NEW}", None,
                address_scope=scope, address_scope_span=span, order_state_claim=claim, order_state_span=None)],
                observations=addr_obs(NEW), **kw), SENTINEL)


def existing_turn(s, text, scope="existing_order", claim="none", cspan=None, addr="7 Hai Bà Trưng, Hoàn Kiếm, Hà Nội"):
    return turn(s, text, F.resp(intent="order_change", requests=[req("change_order_address", "đổi địa chỉ giao đơn vừa đặt", "O1",
                address_scope=scope, address_scope_span="đơn vừa đặt", order_state_claim=claim, order_state_span=cspan)],
                observations=addr_obs(addr)), SENTINEL)


def upd_addr(row):
    return [c for c in F.calls(row, "order.update") if c["args"].get("action") == "update_address"]


extra = {"jev_write_gate": True, "b2_two_tier": False, "b2_max_decisions": 20, "b2_max_tool_calls": 25, "address_scope_gate": True}
with F.Ctx(extra), patch.object(G, "assess", assess):
    # 1) profile_default (H13-057): không order.update, ghi slot address, "ghi nhận"; JEV không thấy nhãn của DeepSeek
    JEV.update(scope="profile_default", claim="none")
    s = F.session("v6p11-profile", decider=planner)
    prior_order(s)
    row = profile_turn(s)
    print("  profile:", row["agent_text"], "| goals", row.get("goals"), "| mem", mem_addr(row), flush=True)
    debug("profile", row)
    check("profile_default: no order.update", not upd_addr(row))
    check("profile_default: address written to profile", any(w.get("value") == NEW for w in mem_addr(row)))
    check("profile_default: reply says recorded", "address_saved_profile" in (row.get("goals") or []) and "ghi nhận" in row["agent_text"])
    check("JEV state hides DeepSeek scope labels", not any(k.startswith(("address_scope", "order_state")) for k in SEEN.get("proposed_keys", [])))
    check("JEV asked address_scope + order_state_claim", {"address_scope", "order_state_claim"} <= set(SEEN.get("opts", [])))

    # 2) existing_order hợp lệ: order.update, KHÔNG ghi hồ sơ
    JEV.update(scope="existing_order", claim="none")
    s = F.session("v6p11-existing", decider=planner)
    oid = ordered(s)
    row = existing_turn(s, "Em đổi địa chỉ giao đơn vừa đặt sang 7 Hai Bà Trưng, Hoàn Kiếm, Hà Nội giúp chị")
    print("  existing:", row["agent_text"], "| goals", row.get("goals"), "| mem", mem_addr(row), flush=True)
    check("existing_order: order.update update_address on the order", len(upd_addr(row)) == 1 and upd_addr(row)[0]["args"].get("order_id") == oid)
    check("existing_order: no profile address write", not mem_addr(row))

    # 3) khách kể đã nhận, hệ thống còn mở → không ghi, hỏi xác minh
    JEV.update(scope="existing_order", claim="delivered")
    s = F.session("v6p11-claim", decider=planner)
    ordered(s)
    row = existing_turn(s, "Đơn vừa đặt chị nhận rồi, em đổi địa chỉ giao đơn vừa đặt sang 7 Hai Bà Trưng, Hoàn Kiếm, Hà Nội",
                        claim="delivered", cspan="chị nhận rồi")
    print("  claim conflict:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("state claim conflict: no write, asks to verify", not upd_addr(row) and not mem_addr(row)
          and "address_state_verify" in (row.get("goals") or []) and "đã cập nhật" not in row["agent_text"])

    # 4–6) lệch phạm vi / lệch lời kể trạng thái / unclear → hỏi lại, không ghi đơn, không ghi hồ sơ
    for label, ds, js, dc, jc in (("scope mismatch", "profile_default", "existing_order", "none", "none"),
                                  ("claim mismatch", "profile_default", "profile_default", "none", "delivered"),
                                  ("scope unclear", "unclear", "unclear", "none", "none")):
        JEV.update(scope=js, claim=jc)
        s = F.session("v6p11-" + label.replace(" ", "-"), decider=planner)
        prior_order(s)
        row = profile_turn(s, scope=ds, span=None if ds == "unclear" else "mấy đơn sau gửi về đây", claim=dc)
        print(f"  {label}:", row["agent_text"], "| goals", row.get("goals"), flush=True)
        debug(label, row)
        check(f"{label}: no order write, no profile write, no 'recorded' claim", not upd_addr(row) and not mem_addr(row)
              and "address_saved_profile" not in (row.get("goals") or []))

    # 7) căn cứ phạm vi không nguyên văn → unclear
    JEV.update(scope="profile_default", claim="none")
    s = F.session("v6p11-span", decider=planner)
    prior_order(s)
    row = profile_turn(s, span="câu này không có trong lời khách")
    items = [i for i in (s.u_turn or {}).get("request_items") or [] if i.get("kind") == "change_order_address"]
    check("non-verbatim scope span → unclear, no writes", items and items[0].get("address_scope") == "unclear"
          and not upd_addr(row) and not mem_addr(row))

    # 8) rút yêu cầu trong cùng lượt → không ghi
    s = F.session("v6p11-withdraw", decider=planner)
    prior_order(s)
    row = profile_turn(s, withdrawn=[{"kind": "change_order_address", "evidence": "địa chỉ mới"}])
    check("withdrawn: no order write, no profile write", not upd_addr(row) and not mem_addr(row))

    # 9) lượt KHÔNG có yêu cầu đổi địa chỉ: ghi địa chỉ như cũ
    s = F.session("v6p11-plain", decider=planner)
    row = turn(s, f"Nhà chị ở {NEW} nha", F.resp(intent="greeting_or_other", observations=addr_obs(NEW)), SENTINEL)
    check("turn without address request: profile write unchanged", any(w.get("value") == NEW for w in mem_addr(row)))

    # 10) ghi hồ sơ thất bại → không báo đã lưu
    JEV.update(scope="profile_default", claim="none")
    s = F.session("v6p11-memfail", decider=planner)
    prior_order(s)
    real_write = s.mem.write_fact

    def failing(cid, slot, *a, **k):
        if slot == "address":
            raise RuntimeError("memory server down")
        return real_write(cid, slot, *a, **k)
    with patch.object(s.mem, "write_fact", failing):
        row = profile_turn(s)
    print("  memfail:", row["agent_text"], "| goals", row.get("goals"), flush=True)
    check("memory write failure: no 'recorded', no order write", "address_saved_profile" not in (row.get("goals") or [])
          and "ghi nhận" not in row["agent_text"] and not upd_addr(row))

    # 11) địa chỉ trùng giá trị đã lưu → vẫn báo ghi nhận
    s = F.session("v6p11-same", decider=planner)
    prior_order(s)
    s.mem.write_fact(s.customer["customer_id"], "address", NEW, "seed", "seed", s.today)
    row = profile_turn(s)
    check("same value already stored: still 'recorded'", "address_saved_profile" in (row.get("goals") or []) and not upd_addr(row))

# 12) tắt cờ: prompt / schema / câu hỏi JEV như v6p10
captured = {}
real_fake = F.fake_call


def capture(prompt, schema, *a, **k):
    captured["prompt"], captured["schema"] = prompt, schema
    return real_fake(prompt, schema, *a, **k)


extra_off = {**extra, "address_scope_gate": False}
with F.Ctx(extra_off), patch.object(G, "assess", assess), patch.object(U, "_call", capture):
    SEEN.clear()
    s = F.session("v6p11-off", decider=planner)
    prior_order(s)
    profile_turn(s)
    props = captured["schema"]["properties"]["requests"]["items"]["properties"]
    check("flag off: schema has no address_scope fields", not any(k.startswith(("address_scope", "order_state")) for k in props))
    check("flag off: prompt has no address scope block", U.ADDRESS_SCOPE_PROMPT.strip()[:40] not in captured["prompt"])
    check("flag off: JEV not asked address_scope", "address_scope" not in SEEN.get("opts", []))

print("v6p11 checks:", passed, "PASS", flush=True)
assert not failed, failed
