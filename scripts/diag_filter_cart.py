"""CHẨN ĐOÁN RIÊNG (không phải cổng đạt, không sửa): V3-055 c1 t4 "Thêm Philips 6.2L nữa, với một bộ màng lọc thay thế cho AirPure Y
luôn nhé." → giỏ có thêm cả MÁY AirPure Y (khách chỉ xin màng lọc). Người dùng yêu cầu 13/11 tách lỗi này ra để chẩn đoán.

Dựng lại đúng lượt bằng output DeepSeek đã ghi trong trace v6 (intent / asks / request_items + target_ref), Jev = bộ quyết
định có kịch bản (report_cart → finish) để chỉ quan sát bước chuẩn bị giỏ. Ghi lại:
  - parser catalog trên câu (find_products) và s.turn_mentioned → danh sách ứng viên P# đưa cho bộ hiểu;
  - c.mentioned SAU bí danh "màng lọc" (FILTER_OF) của _prepare_target;
  - refmap P# của lượt và target_ref DeepSeek chọn;
  - mỗi lần thêm vào giỏ: SKU + nhánh code thêm (mentioned / target_ref / ALL) theo dòng gọi.
Dùng: python scripts/diag_filter_cart.py <trace_v6.jsonl> <out_dir>
"""
import json
import os
import sys
import tempfile
import traceback
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
TRACE, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="diag_filter_"), "d.db").replace("\\", "/")
os.environ["TOOL_TRANSPORT"] = "direct"
os.environ.setdefault("RUN_PROFILE", "kaggle")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ["LLM_CACHE"] = "off"

from core.config import settings  # noqa: E402
from core.llm import deepseek  # noqa: E402
from core.llm.generator import Generator  # noqa: E402
from core.llm.router import Router  # noqa: E402
from harness import agent, audit, planner_table, understanding as U  # noqa: E402
from harness.memory import Memory  # noqa: E402
from harness.tools import ToolBox, find_products, product_name  # noqa: E402

ROWS = {}
for line in open(TRACE, encoding="utf-8"):
    r = json.loads(line)
    if r["scenario_id"] == "V3-055" and r["call"] == "call_1":
        ROWS[r["turn"]] = r


def packed(row):
    u = row.get("understanding") or {}
    ev = u.get("request_evidence") or {}
    return {"intent": u.get("intent") or "greeting_or_other", "flags": list(u.get("flags") or []), "observations": [],
            "requests": [{"kind": it["kind"], "evidence": ev.get(it["kind"], ""), "target_ref": it.get("target_ref"),
                          "condition": None} for it in u.get("request_items") or []],
            "withdrawn": [], "response_to_agent": {"act": "none"}, "asks": list(u.get("asks") or []), "refs": {}, "safety": [],
            "asks_question": bool(u.get("asks_question")), "ambiguity": {"level": "none"}}


QUEUE = []


def script(state, opts):
    st = opts["step"]
    for p in ("answer_ask:", "report_cart", "finish"):
        x = next((s for s in st if s.startswith(p)), None)
        if x:
            return {"step": x, "backend": "script", "ms": 0}
    return {"step": st[-1], "backend": "script", "ms": 0}


patches = [patch.object(settings, k, v) for k, v in dict(arch="target", understanding="", goal_contract=True, contract_v2=True,
                                                         jev_simulated=True, requests_backend="", planner_selector="rules",
                                                         planner_backend="rules", improve_dir="", order_qty=True,
                                                         b2_max_decisions=6, b2_max_tool_calls=13, b2_deadline_s=30.0,
                                                         b2_min_conf=0.0).items()]
patches += [patch.object(U, "_call", lambda prompt, schema, max_tokens: ((QUEUE.pop(0) if QUEUE else {}), 7, 1, None)),
            patch.object(audit, "_jev_sentence", lambda s, k: None),
            patch.object(deepseek.LLM, "json", lambda self, p, **kw: {"claims": []} if "claims" in json.dumps(kw.get("schema") or {})
                         else {"lead": "L0", "policy_refs": [], "attribute_refs": []})]
for p in patches:
    p.start()

mem = Memory("diag:filter_cart")
mem.wipe()
ToolBox.reset_world()
s = agent.CallSession(memory=mem, today="2026-10-17", call_name="call_1", session_id="diag:V3-055:call_1", channel="hotline",
                      channel_identity=None, phone="0944834560", input_mode="text", router=Router("rules"),
                      generator=Generator("offline"), config="full", planner_variant="b2_jev", planner_decider=script)
s.start()

ADDS = []
orig_add = s._cart_add


def traced_add(sku):
    fr = [f for f in traceback.extract_stack(limit=8) if f.filename.endswith("planner_table.py") and "_cart_add" not in (f.line or "")]
    f = fr[-1] if fr else None
    line = (f.line or "?") if f else "?"
    branch = {"add(m_)": "mentioned", "add(sku)": "target_ref", "add(d)": "ALL"}.get(line.strip(), line.strip())
    ADDS.append({"sku": sku, "name": product_name(sku), "branch": branch, "code": line.strip(), "lineno": f.lineno if f else None})
    return orig_add(sku)


s._cart_add = traced_add
report = {"turns": []}
orig_prepare = planner_table._prepare_target


def spy_prepare(c):
    out = orig_prepare(c)
    report["turns"][-1]["c_mentioned_after_alias"] = [product_name(x) for x in c.mentioned]
    report["turns"][-1]["understanding_targets"] = list((c.u or {}).get("targets") or [])
    report["turns"][-1]["cart_source"] = getattr(c, "cart_source", None)
    report["turns"][-1]["accessory_unclear"] = [product_name(x) for x in getattr(c, "cart_unclear", None) or []]
    return out


with patch.object(planner_table, "_prepare_target", spy_prepare):
    for i in (1, 2, 3, 4):
        row = ROWS[i]
        text = row["customer_text"]
        n0 = len(ADDS)
        report["turns"].append({"turn": i, "text": text, "parser_find_products": [product_name(x) for x in find_products(text)]})
        QUEUE[:] = [packed(row)]
        out = s.turn(text)
        t = report["turns"][-1]
        t.update(turn_mentioned=[product_name(x) for x in getattr(s, "turn_mentioned", []) or []],
                 refmap={k: [product_name(x) for x in v.get("skus") or ()] for k, v in s.reqs.refmap.items()
                         if k.startswith("P") and v.get("type") == "product"},
                 deepseek_request_items=(row.get("understanding") or {}).get("request_items"),
                 cart_adds=ADDS[n0:], cart_after=[product_name(x) for x in s.cart], agent_text=out.get("agent_text"))
for p in reversed(patches):
    p.stop()

t4 = report["turns"][-1]
machine = [a for a in t4["cart_adds"] if a["name"].startswith("Máy lọc không khí AirPure Y")]
report["finding"] = {
    "air_purifier_added_at_t4": bool(machine),
    "added_by_branch": [a["branch"] for a in machine],
    "filter_added": any("Màng lọc" in a["name"] for a in t4["cart_adds"]),
    "cart_source_t4": t4.get("cart_source"),
    "candidates_t4": t4["refmap"],
    "cart_after_t4": t4["cart_after"],
    "note": "Nhánh 'target_ref' = refmap P# (dựng từ turn_mentioned, TRƯỚC bí danh màng lọc) → bộ hiểu chọn P# của máy; nhánh "
            "'mentioned' = c.mentioned SAU bí danh. Hai nguồn đối tượng cho cùng một yêu cầu thêm vào giỏ.",
}
json.dump(report, open(os.path.join(OUT, "diag_filter_cart.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(report["finding"], ensure_ascii=False, indent=1))
for t in report["turns"]:
    print(f"t{t['turn']}: parser={t['parser_find_products']} | mentioned_after_alias={t.get('c_mentioned_after_alias')} | "
          f"refmap={t['refmap']} | ds_items={t['deepseek_request_items']} | adds={[(a['name'], a['branch']) for a in t['cart_adds']]} | "
          f"cart={t['cart_after']}")
