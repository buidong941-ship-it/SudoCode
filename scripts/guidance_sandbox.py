"""18/11 candidate: "So sánh trước / sau" một bản nháp hướng dẫn với Jev THẬT — chạy luồng agent đầy đủ (bộ hiểu → truy hồi hướng
dẫn → Jev chọn bước → code thực thi tool → trả lời), hai phiên thử độc lập cùng ngữ cảnh / cấu hình:
    trước = tập nền (rỗng như R0, hoặc các hướng dẫn đã duyệt);  sau = tập nền, thay bản cùng guide_id bằng BẢN NHÁP đang xét.

    python scripts/guidance_sandbox.py --spec <spec.json> --out <thư mục kết quả>

Cô lập (UI gọi script này bằng TIẾN TRÌNH RIÊNG):
- DB bộ nhớ riêng `<out>/sandbox.db` (DATABASE_URL đặt TRƯỚC khi import core), trace riêng `<out>/ui/traces` — không đụng DB / trace /
  feedback của UI, nên phiên thử không vào vòng gap; mock tool (đơn, lịch gọi lại, ticket) là trạng thái trong tiến trình này và
  reset trước MỖI phiên → tạo / sửa / hủy đơn trong phiên thử không phát sinh giao dịch ở cuộc gọi thật đang mở.
- Bản nháp chỉ được khóa vào phiên thử (thay `guidance_pin` sau khi mở phiên); KHÔNG đóng gói, KHÔNG kích hoạt, không đổi
  active.json. Cờ / settings đổi trong tiến trình thử, không hot-switch phiên của UI.
- Cần khóa API thật (DeepSeek / TypeSafe) và profile candidate kiểm hash đạt; thiếu → dừng, không chạy với backend dự phòng
  (kết quả dự phòng không phải "Jev thật"). Không in giá trị khóa.
Spec: {"draft": guide DTO, "draft_prop": id, "draft_payload_sha": ..., "base": "empty" | "approved", "base_guides": [DTO],
       "trials": [câu khách], "context": [câu khách trước đó, phát lại ở cả hai phiên], "two_tier": bool, "phone", "channel",
       "day", "by"}.  Kết quả `<out>/result.json`. Một lần chạy model thật chỉ là kết quả thử, không phải phép đo.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_TRIALS = 5
MAX_CONTEXT = 6
WRITE_TOOLS = ("order.create", "order.update", "order.cancel", "schedule.callback", "handoff.transfer")
ARG_KEYS = ("sku", "order_id", "query", "category", "qty", "action", "lines")


def sides(spec):
    """→ (guides trước, guides sau). Sau = nền bỏ mọi bản cùng guide_id / cùng id với bản nháp, thêm bản nháp."""
    draft = spec["draft"]
    gid = draft.get("guide_id")
    base = [g for g in spec.get("base_guides") or [] if g.get("id") != draft.get("id")]
    after = [g for g in base if not (gid and g.get("guide_id") == gid)] + [draft]
    return base, after


def preview_pin(guides, tag):
    """Khóa tập hướng dẫn cho phiên thử (cùng dạng harness.guidance.pin). Tập rỗng → None (status disabled, như kho rỗng)."""
    if not guides:
        return None
    body = json.dumps(list(guides), ensure_ascii=False, sort_keys=True)
    return {"hash": f"{tag}-" + hashlib.sha256(body.encode()).hexdigest()[:16], "name": tag, "schema": "planner_guidance/1",
            "guides": tuple(guides)}


def turn_view(row):
    lp = (row.get("planner") or {}).get("loop") or {}
    g = lp.get("guidance") or {}
    tt = lp.get("two_tier") or {}
    acts = []
    if tt:
        o = tt.get("outer") or {}
        acts.append(f"tầng ngoài: {tt.get('task') or o.get('task') or o.get('mode')}" + (f" ({o.get('reason')})" if o.get("reason") else ""))
        acts += [f"tầng trong: {s.get('op')}" for s in tt.get("steps") or []]
    acts += [f"{s.get('action')}{':' + s['request_ref'] if s.get('request_ref') else ''}({s.get('status')})" for s in lp.get("steps") or []]
    tools = []
    for t in row.get("tool_calls") or []:
        a = t.get("args") or {}
        tools.append({"name": t["name"], "args": {k: a[k] for k in ARG_KEYS if k in a},
                      "error": bool((t.get("result") or {}).get("error")), "write": t["name"] in WRITE_TOOLS})
    ui = row.get("ui") or {}
    return {"customer_text": row.get("customer_text"),
            "agent_text": ui.get("emitted_text") if ui.get("emitted_text") is not None else row.get("agent_text"),
            "goals": row.get("goals") or [], "actions": acts,
            "two_tier": {k: tt.get(k) for k in ("task", "outcome", "jev_calls", "tool_calls")} if tt else None,
            "guidance": {k: g.get(k) for k in ("status", "selected", "supplied_to_planner", "candidates", "filtered", "tokens_est", "error")},
            "tools": tools, "latency_ms": (row.get("latency") or {}).get("total_ms")}


def run_side(E, ToolBox, spec, text, guides, tag, out_dir):
    """Một phiên thử: mock reset, namespace mới, mở phiên, khóa tập hướng dẫn, phát lại ngữ cảnh, câu thử."""
    t0 = time.perf_counter()
    ToolBox.reset_world()
    eng = E.Engine(f"sandbox-{tag}-{os.path.basename(out_dir)}", "full")
    eng.two_tier = bool(spec.get("two_tier", True))
    eng.use_guidance = False                         # không đọc active.json: tập hướng dẫn của phiên thử do spec quyết định
    rec = {"side": tag, "guides": [g["id"] for g in guides], "turns": [], "error": None}
    try:
        eng.start_call(spec.get("phone") or "0900111222", spec.get("channel") or "hotline", spec.get("day") or None)
        pin = preview_pin(guides, f"sandbox-{tag}")
        eng.sess.guidance_pin = pin
        eng.calls[-1].update(guidance_hash=(pin or {}).get("hash"), mode=E.mode_code(eng.two_tier, bool(pin)))
        rec.update(mode=eng.calls[-1]["mode"], guidance_hash=(pin or {}).get("hash"))
        for i, t in enumerate(list(spec.get("context") or [])[:MAX_CONTEXT] + [text]):
            v = turn_view(eng.say(t, event_id=f"{tag}:{i}"))
            v["is_context"] = i < len(list(spec.get("context") or [])[:MAX_CONTEXT])
            rec["turns"].append(v)
    except Exception as e:  # noqa: BLE001 — lỗi một phiên thử: ghi lại, không che
        rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        rec["traceback"] = traceback.format_exc()[-1500:]
    finally:
        try:
            eng.end_call()
        except Exception as e:  # noqa: BLE001
            rec["error"] = rec["error"] or f"end_call {type(e).__name__}: {str(e)[:200]}"
    rec["wall_ms"] = int((time.perf_counter() - t0) * 1000)
    rec["writes"] = [t for v in rec["turns"] for t in v["tools"] if t["write"]]
    return rec


def run_spec(spec, out_dir, E=None, require_keys=True):
    """Chạy mọi câu thử (trước / sau). Trong tiến trình hiện tại: settings + trace UI được trả lại sau khi xong."""
    if E is None:
        from ui import engine as E  # noqa: N811
    from core.config import settings
    from harness.tools import ToolBox
    boot = E.startup_check()
    if not E.CANDIDATE:
        raise SystemExit("profile không phải candidate (UI_PROFILE=b2_integ_tt)")
    if require_keys and not (boot.get("ok") and all((boot.get("keys_present") or {}).values())):
        raise SystemExit("thiếu khóa API hoặc cấu hình lệch — không chạy (kết quả dự phòng không phải Jev thật): "
                         + "; ".join(boot.get("mismatch") or []) + " " + json.dumps(boot.get("keys_present")))
    trials = [t.strip() for t in spec.get("trials") or [] if t and t.strip()][:MAX_TRIALS]
    if not trials:
        raise SystemExit("không có câu thử")
    before, after = sides(spec)
    keep = {k: getattr(settings, k) for k in ("b2_two_tier", "planner_guidance_dir")}
    old_traces = E.TRACES
    E.TRACES = os.path.join(out_dir, "ui", "traces")
    res = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "by": spec.get("by"), "draft_prop": spec.get("draft_prop"),
           "draft_payload_sha": spec.get("draft_payload_sha"), "draft_version": spec["draft"].get("version"), "base": spec.get("base"),
           "two_tier": bool(spec.get("two_tier", True)), "context": list(spec.get("context") or [])[:MAX_CONTEXT],
           "before_guides": [g["id"] for g in before], "after_guides": [g["id"] for g in after],
           "profile": E.PROFILE_INFO.get("profile"), "code": {k: (E.PROFILE_INFO.get("code") or {}).get(k) for k in ("status", "freeze", "checked")},
           "backend": {"keys_present": boot.get("keys_present"), "label": boot.get("label")}, "trials": []}
    try:
        for i, text in enumerate(trials):
            res["trials"].append({"text": text, "before": run_side(E, ToolBox, spec, text, before, f"t{i}-truoc", out_dir),
                                  "after": run_side(E, ToolBox, spec, text, after, f"t{i}-sau", out_dir)})
    finally:
        E.TRACES = old_traces
        for k, v in keep.items():
            setattr(settings, k, v)
        ToolBox.reset_world()
    res["note"] = ("Kết quả thử với model thật, mỗi câu một lần: căn cứ để đọc khi duyệt, không phải phép đo. "
                   "'Đưa vào Jev' chỉ cho biết hướng dẫn có trong payload, không chứng minh tác dụng.")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    # cô lập: phải đặt TRƯỚC khi import ui.engine / core (settings + engine đọc env lúc import)
    os.environ["UI_DATA_DIR"] = os.path.join(out, "ui")
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(out, "sandbox.db").replace("\\", "/")
    os.environ["PLANNER_GUIDANCE_DIR"] = ""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    spec = json.load(open(a.spec, encoding="utf-8"))
    res = run_spec(spec, out)
    print(json.dumps({"trials": len(res["trials"]), "errors": [s["error"] for t in res["trials"] for s in (t["before"], t["after"]) if s["error"]],
                      "out": out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
