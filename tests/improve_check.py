"""Kiểm tra khung cơ chế cải tiến (plan 01/11 mục D): tách biệt core, D1 collect, D2/D3 pending→approved, D4, D5.

Chạy: python tests/improve_check.py   (không cần mạng, không cần model; mọi dữ liệu ghi vào thư mục tạm)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from improve import collect as C  # noqa: E402
from improve import loader as L  # noqa: E402
from improve import store as S  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import compare_rounds as CR  # noqa: E402

FAILS = []


def ok(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL:", msg)


def imports_of(path):
    src = open(path, encoding="utf-8").read()
    return set(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M))


# 1. tách biệt: core không import improve; improve không import core/harness/eval
core_files = [os.path.join(d, f) for top in ("harness", "core", "eval", "mcp_servers")
              for d, _, fs in os.walk(os.path.join(ROOT, top)) for f in fs if f.endswith(".py")]
core_files.append(os.path.join(ROOT, "run_eval.py"))
HOOK = os.path.join(ROOT, "harness", "improve_hook.py")   # điểm nối DUY NHẤT (mục E), chỉ được dùng improve.loader
for f in core_files:
    bad = {m for m in imports_of(f) if m == "improve" or m.startswith("improve.")}
    if os.path.abspath(f) == HOOK:
        ok(bad <= {"improve.loader"}, f"harness/improve_hook.py chỉ được import improve.loader, có {bad}")
        continue
    ok(not bad, f"{os.path.relpath(f, ROOT)} import {bad} — core phải tách khỏi improve/ (chỉ harness/improve_hook.py)")
for f in os.listdir(os.path.join(ROOT, "improve")):
    if f.endswith(".py"):
        bad = {m for m in imports_of(os.path.join(ROOT, "improve", f))
               if m.split(".")[0] in ("harness", "core", "eval", "mcp_servers", "run_eval")}
        ok(not bad, f"improve/{f} import {bad} — improve/ chỉ đọc file, không gọi core")

tmp = tempfile.mkdtemp(prefix="improve_check_")
root = os.path.join(tmp, "imp")


def row(sid, call, turn, cust, agent, goals=("quote",), guard=None, branches=()):
    return {"run_id": "t-datagen/out_btc_like_final_v1/final/dev", "config": "full", "scenario_id": sid,
            "call": call, "turn": turn, "customer_text": cust, "agent_text": agent, "goals": list(goals),
            "router": {"intent": "policy_question"}, "guardrail": guard or {"problems": [], "action": None},
            "planner": {"backend": "rules", "branches": [{"branch": b, "reason": r} for b, r in branches]},
            "tool_calls": [{"name": "pricing.get_quote", "args": {}, "result": {}}]}


rows = [
    row("S1", "call_1", 1, "Máy này giá bao nhiêu?", "Dạ giá 5.200.000đ ạ."),
    row("S1", "call_1", 2, "Hai năm sau có hoàn tiền không?", "Dạ em chưa có thông tin ạ.", ("no_info",),
        branches=[("policy_gap", "asked 730d > max 30d")]),
    row("S1", "call_2", 1, "Như anh đã nói hôm trước, giao về 5 Trần Phú nhé", "Dạ vâng.", ("order_created",),
        guard={"problems": ["số tiền lạ 9.990.000"], "action": "safe_template", "coverage": []}),
    row("S2", "call_1", 1, "Chào em", "Dạ chào anh.", ("greet",), guard={"problems": [], "action": "regenerated",
                                                                      "coverage": ["x"], "rejected": ["a", "b", "c"]}),
]
rows.append(dict(rows[0], config="baseline_no_memory"))
trace = os.path.join(tmp, "dev", "full.jsonl")
os.makedirs(os.path.dirname(trace))
with open(trace, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
report = {"system": {
    "repeat_question_rate": {"value": 10, "examples": [{"scenario": "S1", "call": "call_2", "turn": 1,
                                                        "slot": "address", "type": "open", "text": "Địa chỉ ạ?"}]},
    "hallucination_rate": {"value": 5, "price_promo_only": {"value": 6},
                           "examples": [{"scenario": "S1", "call": "call_1", "turn": 1, "field": "price_vnd",
                                         "claimed": 1, "truth": 2}]},
    "task_success_rate": {"value": 50, "failures": [{"scenario": "S1", "call": "call_2", "hard_case": "hc",
                                                     "reasons": ["không có tool call order.create khớp args_match"]}]},
    "context_carryover_rate": {"value": 80}, "guardrail_violations": 0}}
rep_path = os.path.join(tmp, "dev", "report.json")
json.dump(report, open(rep_path, "w", encoding="utf-8"), ensure_ascii=False)

# 2. D1 collect
gaps = C.collect(trace, rep_path)
types = sorted((g["type"], g.get("subtype")) for g in gaps)
want = [("claim_wrong", "price_vnd"), ("customer_repeat", None), ("guardrail", "regenerated"),
        ("guardrail", "safe_template"), ("no_info", None), ("repeat_question", "address"), ("task_fail", "hc")]
ok(types == want, f"loại gap {types} != {want}")
g_no = next(g for g in gaps if g["type"] == "no_info")
ok(g_no["detail"]["reason"] == "asked 730d > max 30d" and g_no["context"][0]["turn"] == 1,
   f"no_info thiếu lý do planner / ngữ cảnh: {g_no}")
g_tf = next(g for g in gaps if g["type"] == "task_fail")
ok(g_tf["turn"] is None and len(g_tf["context"]) == 1, "task_fail phải kèm toàn bộ lượt của cuộc gọi")
ok(len(next(g for g in gaps if g.get("subtype") == "regenerated")["detail"]["rejected"]) == 2, "rejected cắt còn 2")
ok(len({g["id"] for g in gaps}) == len(gaps), "id gap phải duy nhất")
gp = os.path.join(root, "gaps.jsonl")
ok(C.write(gaps, gp) == len(gaps) and C.write(gaps, gp, append=True) == 0, "append không được nhân bản gap")
for bad in ("datagen/out_btc_like_final_v1/final/holdout/full.jsonl", "runs/x/out_nat/test/full.jsonl"):
    try:
        C.check_dev_only(bad)
        ok(False, f"không chặn {bad}")
    except C.LeakError:
        pass
leak = os.path.join(tmp, "leak.jsonl")
with open(leak, "w", encoding="utf-8") as fh:
    fh.write(json.dumps(dict(rows[0], run_id="r-datagen/out_btc_like_final_v1/final/holdout")) + "\n")
try:
    C.collect(leak)
    ok(False, "run_id holdout phải bị chặn")
except C.LeakError:
    pass

# 3. D2 đề xuất: luật chặn
FAQ = {"kind": "faq", "payload": {"topic": "hoàn tiền sau thời hạn",
                                  "question": "Mua lâu rồi có hoàn tiền được không?",
                                  "answer": "Chính sách chỉ áp dụng trong thời hạn đổi trả ghi trong tài liệu; ngoài thời hạn em ghi nhận và báo lại.",
                                  "policy_refs": ["03-02"]}, "source_gaps": [g_no["id"]]}
blocked = [
    {"kind": "faq", "payload": dict(FAQ["payload"], answer="Giá chỉ 5.200.000đ thôi ạ")},
    {"kind": "faq", "payload": dict(FAQ["payload"], answer="Được giảm 10% ạ")},
    {"kind": "playbook", "payload": {"trigger": "hỏi giá", "instruction": "báo năm triệu hai trăm nghìn"}},
    {"kind": "exemplar", "payload": {"customer_text": "x", "agent_text": "Gọi em số 0912345678 nhé"}},
    {"kind": "exemplar", "payload": {"customer_text": "x", "agent_text": "Em cam kết giao trong 1 ngày ạ"}},
    {"kind": "cue", "payload": {"slot": "address", "pattern": "giao (về"}},
    {"kind": "faq", "payload": {"topic": "x", "question": "", "answer": "y"}},
    {"kind": "rule", "payload": {}},
]
for b in blocked:
    try:
        S.propose(b, root=root)
        ok(False, f"không chặn đề xuất {b}")
    except S.ProposalError:
        pass
st, pid = S.propose(FAQ, root=root)
ok(st == "pending" and pid.startswith("P-faq-"), "faq hợp lệ phải vào pending")
ok(S.propose(FAQ, root=root) == ("pending", pid), "đề xuất trùng phải trả id cũ, không tạo mới")
st2, pid2 = S.propose({"kind": "cue", "payload": {"slot": "address", "pattern": r"giao (?:về|tới) "}}, root=root)

# 4. D3 duyệt: chỉ approved tới được agent; cần người duyệt
ok(L.load_approved(root)["items"]["faq"] == [], "pending không được nạp")
try:
    S.approve(pid, "", root=root)
    ok(False, "approve không có --by phải lỗi")
except S.ProposalError:
    pass
S.approve(pid, "tester", "khớp 03-02", root=root)
S.reject(pid2, "tester", "cue quá rộng", root=root)
got = L.load_approved(root)
ok([x["id"] for x in got["items"]["faq"]] == [pid] and got["items"]["cue"] == [], f"approved sai: {got['items']}")
h1 = got["hash"]
events = [r["event"] for r in S.read_log(root)]
ok(events.count("propose") == 2 and "approve" in events and "reject" in events, f"log thiếu sự kiện: {events}")
appr = S.find(pid, root)[1]
ok(appr["review"]["by"] == "tester" and appr["review"]["from"] == "pending", "review phải ghi người và trạng thái cũ")
# file approved bị sửa tay thêm số tiền → loader bỏ qua
tam_id = S.propose({"kind": "playbook", "payload": {"trigger": "khách hỏi quà", "instruction": "tra tool rồi mới báo"}},
                   root=root)[1]
S.approve(tam_id, "tester", root=root)
f = os.path.join(root, "approved", f"{tam_id}.json")
d = json.load(open(f, encoding="utf-8"))
d["payload"]["instruction"] = "báo quà trị giá 690.000đ"
json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False)
got = L.load_approved(root)
ok(got["items"]["playbook"] == [] and got["skipped"] and got["skipped"][0][0] == tam_id, "loader phải bỏ file approved vi phạm")
os.remove(f)

# 5. D5 vòng + quay lui
S.save_round("r0", [f"dev={rep_path}"], by="tester", root=root)
pid3 = S.propose({"kind": "playbook", "payload": {"trigger": "khách hỏi văn bản", "instruction": "nói không có thông tin"}},
                 root=root)[1]
S.approve(pid3, "tester", root=root)
ok(S.approved_hash(root) != h1, "hash approved phải đổi khi thêm đề xuất")
try:
    S.save_round("r0", root=root)
    ok(False, "trùng tên vòng phải lỗi")
except S.ProposalError:
    pass
res = S.rollback("r0", "tester", "thử", root=root)
ok(res["removed"] == [pid3] and S.find(pid3, root)[0] == "pending", f"quay lui sai: {res}")
ok(S.approved_hash(root) == h1, "sau quay lui hash phải về như vòng r0")
ok(S.load_round("r0", root)["reports_data"]["dev"]["system"]["task_success_rate"]["value"] == 50, "round phải lưu report")


def rep(tsr, hr, fails=()):
    return {"system": {"task_success_rate": {"value": tsr, "failures": [{"scenario": s, "call": "call_2"} for s in fails]},
                       "hallucination_rate": {"value": hr, "price_promo_only": {"value": hr}},
                       "repeat_question_rate": {"value": 10}, "context_carryover_rate": {"value": 80},
                       "guardrail_violations": 0}}


ok(S.rollback_decision({"dev": rep(70, 5)}, {"dev": rep(66.9, 5)})["rollback"], "TSR tụt 3,1 phải quay lui")
ok(not S.rollback_decision({"dev": rep(70, 5)}, {"dev": rep(68, 5)})["rollback"], "TSR tụt 2 không quay lui")
ok(S.rollback_decision({"dev": rep(70, 5)}, {"dev": rep(75, 5.1)})["rollback"], "HR tăng phải quay lui")
ok(S.rollback_decision({"dev": rep(70, 5), "holdout": rep(60, 5)},
                       {"dev": rep(72, 5), "holdout": rep(50, 5)})["reasons"][0].startswith("holdout"), "xét từng bộ")

# 6. D4 compare_rounds
md = CR.compare([("r0", {"dev": rep(60, 6, ["A", "B"])}), ("r1", {"dev": rep(70, 6, ["B", "C"])})],
                spread={"tsr": 2.0})
ok("Ca được sửa (1): A/call_2" in md and "Ca mới trượt (1): C/call_2" in md, "compare thiếu ca sửa/trượt")
ok("| Task Success Rate (%) | 60 | 70 | 10 | tốt hơn |" in md, f"dòng TSR sai:\n{md}")
md2 = CR.compare([("r0", {"dev": rep(60, 6)}), ("r1", {"dev": rep(63, 6)})], spread={"tsr": 2.0})
ok("≈ trong dao động" in md2, "Δ 3 ≤ 2·sd phải là trong dao động")

# 7. CLI
env = dict(os.environ, PYTHONIOENCODING="utf-8")
cli = [sys.executable, "-m", "improve", "--root", root]
r = subprocess.run(cli + ["status"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
ok(r.returncode == 0 and "approved: 1" in r.stdout and "vòng r0" in r.stdout, f"status lỗi: {r.stdout}{r.stderr}")
bad_rep = os.path.join(tmp, "bad.json")
json.dump(rep(40, 9), open(bad_rep, "w", encoding="utf-8"))
r = subprocess.run(cli + ["check", "--prev", "r0", "--report", f"dev={bad_rep}"], cwd=ROOT, capture_output=True,
                   text=True, encoding="utf-8", env=env)
ok(r.returncode == 2 and '"rollback": true' in r.stdout, f"check phải trả mã 2: {r.returncode} {r.stdout}{r.stderr}")
r = subprocess.run(cli + ["review", "approve", "P-faq-00000000", "--by", "x"], cwd=ROOT, capture_output=True,
                   text=True, encoding="utf-8", env=env)
ok(r.returncode != 0 and "không thấy" in r.stderr, "approve id không có phải báo lỗi")

print("TẤT CẢ OK" if not FAILS else f"{len(FAILS)} LỖI")
sys.exit(1 if FAILS else 0)
