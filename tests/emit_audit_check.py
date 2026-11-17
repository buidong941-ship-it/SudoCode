"""Kiểm XÁC ĐỊNH (Kaggle CPU) đường gửi phản hồi tách khỏi audit hậu kỳ + cách đo latency (13/11, người dùng duyệt).

Audit = hàm giả (chậm / lỗi / quá hạn), DeepSeek = phản hồi đóng gói, generator offline. Không gọi model thật — phần tích hợp với
DeepSeek / Jev thật nằm ở job dev (scripts/latency_report_emit.py --strict đọc trace thật).

E1 audit chậm: callback on_emit nhận câu TRƯỚC khi audit xong; turn() trả về không đợi audit; TTFT = Total = tới emit;
   response_ready ≤ total ≤ end_to_end; audit_status pending lúc trả về, ok sau khi drain; turn_complete ≥ audit
E2 audit chạy trên ĐÚNG chuỗi đã gửi (sha outbox = sha trace = chuỗi audit nhận); guardrail chạy trước emit
E3 khách gửi lượt tiếp khi audit lượt trước chưa xong: mỗi kết quả ghi vào đúng lượt của nó, theo thứ tự; không đổi trạng thái
   phiên (history / known) của lượt mới
E4 audit lỗi: audit_status=error + audit_error rõ, claims / questions rỗng, câu đã gửi không đổi
E5 kết thúc phiên: end() đợi mọi audit, không còn pending
E6 quá hạn khi drain: audit_status=timeout; kết quả về muộn KHÔNG ghi vào trace
E7 AUDIT_ASYNC=0: vẫn emit thật, turn() đợi audit → end_to_end gồm phần chờ, total vẫn tại emit
E8 run_eval: dòng trace chỉ ghi sau khi audit xong (đủ claims), emit_check nhận đúng sha; Call Brief đo cho call_1; lịch sử seed
   nạp offline TRƯỚC start() (brief nhận ra khách cũ, không dựng lại brief); offline ghi riêng
E9 scripts/latency_report_emit.py: bỏ 3 lượt warm-up theo thứ tự emit, p95 công thức BTC (eval/reference_eval.p95, không sửa),
   số mẫu hợp lệ + cảnh báo < 100, chỉ số chẩn đoán riêng
Dùng: python tests/emit_audit_check.py
"""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
tmp = tempfile.mkdtemp(prefix="emit_audit_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "e.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

from core.config import settings  # noqa: E402
from core.llm import deepseek  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, audit, understanding as U  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox  # noqa: E402

FAIL, PASS = [], [0]


def ok(group, name, got, want=True):
    if got == want:
        PASS[0] += 1
        print(f"OK   [{group}] {name}", flush=True)
    else:
        FAIL.append((group, name))
        print(f"FAIL [{group}] {name}: got={got!r} want={want!r}", flush=True)


def resp(**kw):
    d = {"intent": "greeting_or_other", "flags": [], "observations": [], "requests": [], "withdrawn": [],
         "response_to_agent": {"act": "none"}, "asks": [], "refs": {}, "safety": [], "asks_question": False,
         "ambiguity": {"level": "none"}}
    d.update(kw)
    return d


QUEUE = []
PRICE_Q = resp(intent="price_promo", asks=["price"], asks_question=True)
SEEN = []                      # (thread, text) audit nhận
MODE = {"sleep": 0.0, "fail": False}


def fake_audit(text, known, meta, cands):
    SEEN.append(text)
    time.sleep(MODE["sleep"])
    if MODE["fail"]:
        raise RuntimeError("audit down (giả lập)")
    meta["audit"] = {"status": "ok", "pipeline": "target_v1", "backend": "questions=fake;claims=fake", "cert": None, "cascade": None}
    meta["ms"] = 5
    return [{"slot": "other", "type": "open", "text": text}], [{"field": "echo", "value": text}]


BASE = dict(arch="target", understanding="", goal_contract=True, contract_v2=True, jev_simulated=True, requests_backend="",
            planner_selector="rules", planner_backend="rules", improve_dir="", order_qty=True, planner_variant="b1",
            audit_async=True, audit_drain_timeout_s=30.0)


class Ctx:
    def __init__(self, extra=None):
        self.ps = [patch.object(settings, k, v) for k, v in {**BASE, **(extra or {})}.items()]
        self.ps += [patch.object(U, "_call", lambda prompt, schema, max_tokens: ((QUEUE.pop(0) if QUEUE else resp()), 7, 1, None)),
                    patch.object(U, "understand_record", lambda summary, today: ({}, {"calls": 0, "ms": 0, "error": None})),
                    patch.object(audit, "run", fake_audit),
                    patch.object(deepseek.LLM, "json", lambda self, p, **kw: {"claims": []} if "claims" in json.dumps(kw.get("schema") or {})
                                 else {"lead": "L0", "policy_refs": [], "attribute_refs": []})]

    def __enter__(self):
        for p in self.ps:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self.ps):
            p.stop()


EMITS = []


def session(name):
    mem = Memory(f"emitcheck:{name}")
    mem.wipe()
    ToolBox.reset_world()
    s = agent.CallSession(memory=mem, today="2026-10-15", call_name="call_1", session_id=f"{name}:call_1", channel="hotline",
                          channel_identity=None, phone="0911222333", input_mode="text", router=Router("rules"),
                          generator=Generator("offline"), config="full",
                          on_emit=lambda m: EMITS.append({**m, "recv": time.perf_counter(), "thread": threading.get_ident()}))
    s.start()
    return s


def say(s, text, d):
    QUEUE[:] = [d]
    t0 = time.perf_counter()
    row = s.turn(text)
    return row, t0, time.perf_counter()


# ---------------------------------------------------------------- E1 / E2: audit chậm, emit trước, đúng chuỗi
with Ctx():
    MODE.update(sleep=1.2, fail=False); SEEN.clear(); EMITS.clear()
    s = session("e1")
    row, t0, t_ret = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    lat = row["latency"]
    em = EMITS[-1]
    ok("E1", "on_emit được gọi (callback thật) trước khi turn() trả về, cùng thread phục vụ lượt",
       (len(EMITS), em["recv"] < t_ret, em["thread"] == threading.get_ident()), (1, True, True))
    ok("E1", "turn() trả về KHÔNG đợi audit (chậm 1,2 s); trạng thái pending", (t_ret - t0 < 1.0, row["audit_status"]), (True, "pending"))
    ok("E1", "TTFT = Total = tới emit; response_ready ≤ total ≤ end_to_end; đo kiểu emit_v1",
       (lat["ttft_ms"] == lat["total_ms"], lat["response_ready_ms"] <= lat["total_ms"] <= lat["end_to_end_ms"], lat["measure"]),
       (True, True, "emit_v1"))
    s.drain_audits()
    lat = row["latency"]
    ok("E1", "sau drain: audit ok, claims / questions có, audit_ms ≥ 1200, turn_complete ≥ audit_ms, ≥ end_to_end",
       (row["audit_status"], bool(row["claims"]) and bool(row["questions"]), lat["audit_ms"] >= 1200,
        lat["turn_complete_ms"] >= lat["audit_ms"] and lat["turn_complete_ms"] >= lat["end_to_end_ms"]), ("ok", True, True, True))
    ok("E2", "audit chạy trên ĐÚNG chuỗi đã gửi: outbox = trace = chuỗi audit nhận, sha khớp",
       (s.outbox[-1]["text"] == row["agent_text"] == SEEN[-1] == row["claims"][0]["value"],
        s.outbox[-1]["sha256"] == row["emitted"]["sha256"] == em["sha256"]), (True, True))
    ok("E2", "guardrail chạy trước emit (trace có guardrail của câu đã gửi)", isinstance(row.get("guardrail"), dict), True)

# ---------------------------------------------------------------- E3: khách gửi lượt tiếp khi audit lượt trước chưa xong
with Ctx():
    SEEN.clear(); EMITS.clear()
    s = session("e3")
    MODE.update(sleep=1.0)
    r1, _, _ = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    MODE.update(sleep=0.05)
    r2, _, t2 = say(s, "Còn AirPure X thì sao em?", PRICE_Q)
    ok("E3", "lượt 2 chạy ngay khi audit lượt 1 còn chạy", (r1["audit_status"], r2["audit_status"]), ("pending", "pending"))
    time.sleep(0.3)
    hist, known = list(s.history), dict(s.known)
    r3, _, _ = say(s, "Ok em", resp())
    ok("E3", "audit lượt 2 xong trước lượt 1 nhưng chưa ghi (giữ thứ tự lượt): lượt 1 chưa xong → cả hai còn pending",
       (r1["audit_status"], r2["audit_status"]), ("pending", "pending"))
    s.drain_audits()
    ok("E3", "mỗi kết quả ghi vào đúng lượt của nó", (r1["claims"][0]["value"] == r1["agent_text"], r2["claims"][0]["value"] == r2["agent_text"],
                                                    r3["claims"][0]["value"] == r3["agent_text"]), (True, True, True))
    ok("E3", "finalize không đổi trạng thái phiên của lượt mới (history / known)", (s.history[:len(hist)] == hist, all(s.known.get(k) == v for k, v in known.items())),
       (True, True))

# ---------------------------------------------------------------- E4: audit lỗi
with Ctx():
    MODE.update(sleep=0.0, fail=True); SEEN.clear(); EMITS.clear()
    s = session("e4")
    row, _, _ = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.drain_audits()
    ok("E4", "audit lỗi → audit_status=error, audit_error rõ, claims / questions rỗng (không bịa)",
       (row["audit_status"], "audit down" in (row.get("audit_error") or ""), row["claims"], row["questions"]), ("error", True, [], []))
    ok("E4", "câu đã gửi không bị sửa", row["agent_text"] == s.outbox[-1]["text"] == EMITS[-1]["text"], True)
    MODE.update(fail=False)

# ---------------------------------------------------------------- E5: kết thúc phiên đợi audit
with Ctx():
    MODE.update(sleep=0.5); EMITS.clear()
    s = session("e5")
    rows = [say(s, t, PRICE_Q)[0] for t in ("Samsung AX40 giá bao nhiêu em?", "AirPure X giá sao em?")]
    s.end()
    ok("E5", "end() đợi mọi audit: không còn pending, đủ claims", ([r["audit_status"] for r in rows], s._audits, all(r["claims"] for r in rows)),
       (["ok", "ok"], [], True))

# ---------------------------------------------------------------- E6: quá hạn khi drain → timeout, kết quả muộn không ghi
with Ctx():
    MODE.update(sleep=1.5)
    s = session("e6")
    row, _, _ = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    s.drain_audits(timeout_s=0.2)
    snap = json.dumps({k: row.get(k) for k in ("audit_status", "claims", "questions", "audit")}, ensure_ascii=False, default=str)
    ok("E6", "drain quá hạn → audit_status=timeout + lỗi ghi rõ, claims rỗng", (row["audit_status"], "chưa xong" in row.get("audit_error", ""), row["claims"]),
       ("timeout", True, []))
    time.sleep(1.6)
    ok("E6", "kết quả audit về muộn KHÔNG ghi đè trace", json.dumps({k: row.get(k) for k in ("audit_status", "claims", "questions", "audit")},
                                                                    ensure_ascii=False, default=str) == snap, True)

# ---------------------------------------------------------------- E7: AUDIT_ASYNC=0
with Ctx({"audit_async": False}):
    MODE.update(sleep=0.6)
    s = session("e7")
    row, t0, t_ret = say(s, "Samsung AX40 giá bao nhiêu em?", PRICE_Q)
    lat = row["latency"]
    ok("E7", "đồng bộ: turn() đợi audit (end_to_end ≥ 600 ms), total vẫn tại emit (< end_to_end), audit ok khi trả về",
       (lat["end_to_end_ms"] >= 600, lat["total_ms"] < lat["end_to_end_ms"], row["audit_status"]), (True, True, "ok"))

# ---------------------------------------------------------------- E8: run_eval — trace sau audit, emit_check, Call Brief
import run_eval  # noqa: E402

with Ctx():
    MODE.update(sleep=0.3)
    scen = json.load(open("test_set/public_sample/SAMPLE-01.json", encoding="utf-8"))
    seeded = copy.deepcopy(scen)
    first = sorted(seeded["calls"], key=lambda c: int(c.split("_")[1]))[0]
    seeded["calls"][first]["seed_history"] = [{"session_id": "OLD-EMIT-1", "channel": "hotline", "date": "2026-10-01", "outcome": "khac",
                                                "summary": "Khách hỏi giá máy lọc không khí AirPure X cho phòng 25m2, hẹn suy nghĩ thêm."}]
    sid, rows = run_eval._run_scenario(seeded, "full", "emitcheck", "rules", "offline")
    good = [r for r in rows if not r.get("error")]
    ok("E8", "kịch bản chạy hết, không lỗi", (len(good) == len(rows), len(rows) > 0), (True, True))
    ok("E8", "dòng trace ghi SAU khi audit xong: mọi lượt audit_status=ok, có claims", (sorted({r.get("audit_status") for r in good}), all(r.get("claims") for r in good)),
       (["ok"], True))
    ok("E8", "backend nhận đúng câu đã emit (emit_check received + sha_match) ở mọi lượt",
       all(r["emit_check"]["received"] and r["emit_check"]["sha_match"] for r in good), True)
    t1 = [r for r in good if r["turn"] == 1]
    ok("E8", "Call Brief ghi cho MỌI cuộc gọi (kể cả call_1), kèm phần offline ghi riêng",
       (all(isinstance(r.get("call_brief_latency_ms"), int) for r in t1), all("call_brief_offline" in r for r in t1)), (True, True))
    c1 = next(r for r in t1 if r["call"] == first)
    ok("E8", "lịch sử seed nạp offline TRƯỚC start(): brief call_1 nhận ra khách cũ, offline ghi 1 phiên seed",
       ((c1.get("call_brief") or {}).get("is_returning"), c1["call_brief_offline"]["seed_sessions"]), (True, 1))
    trace_path = os.path.join(tmp, "full.jsonl")
    with open(trace_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------- E9: báo cáo latency riêng
spec = importlib.util.spec_from_file_location("btc_ref", os.path.join(ROOT, "eval", "reference_eval.py"))
btc = importlib.util.module_from_spec(spec); spec.loader.exec_module(btc)
out_dir = os.path.join(tmp, "lat")
p = subprocess.run([sys.executable, "scripts/latency_report_emit.py", "--trace", f"full={trace_path}", "--out", out_dir],
                   capture_output=True, text=True, encoding="utf-8")
ok("E9", "latency_report chạy được", p.returncode, 0)
if p.returncode == 0:
    rep = json.load(open(os.path.join(out_dir, "latency_report.json"), encoding="utf-8"))["configs"]["full"]
    good_sorted = sorted([r for r in rows if not r.get("error")], key=lambda r: r["latency"]["emit_wall_ts"])
    kept = good_sorted[3:]
    totals = [r["latency"]["total_ms"] for r in kept]
    ok("E9", "bỏ đúng 3 lượt warm-up đầu theo thứ tự emit; n hợp lệ = số còn lại",
       (rep["warmup_excluded"], rep["n_valid_turns"]), (3, len(kept)))
    ok("E9", "p95 dùng đúng công thức BTC (eval/reference_eval.p95) trên các lượt còn lại",
       (rep["total"]["p95_ms"], rep["ttft"]["p95_ms"]), (int(btc.p95(totals)), int(btc.p95([r["latency"]["ttft_ms"] for r in kept]))))
    ok("E9", "cảnh báo khi < 100 lượt hợp lệ", bool(rep["warning"]) == (len(kept) < 100), True)
    ok("E9", "chỉ số chẩn đoán riêng (response_ready / post / end_to_end / audit / turn_complete) + trạng thái audit",
       (all(k in rep["diagnostic"] for k in ("response_ready_ms", "post_ms", "end_to_end_ms", "audit_ms", "turn_complete_ms")),
        rep["audit_status"].get("ok")), (True, len(good_sorted)))
else:
    print(p.stdout[-2000:], p.stderr[-2000:])

print(f"\n{PASS[0]} OK, {len(FAIL)} lỗi")
if FAIL:
    print("LỖI:", FAIL)
sys.exit(1 if FAIL else 0)
