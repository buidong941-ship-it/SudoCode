"""Lớp chạy agent cho UI — gọi core đúng như `run_eval.py`, không sửa core, không dùng chung DB với lần chạy đo.

Tách biệt:
- core (harness/, core/, eval/) không import ui/ (tests/ui_check.py kiểm tra);
- UI có DB bộ nhớ riêng `data/ui/memory.db` và namespace riêng `ui:<config>:<tên demo>`, nên không đụng DB / namespace đo;
- env phải đặt TRƯỚC khi import harness (settings đọc env lúc import): profile được chọn MỘT LẦN cho cả tiến trình qua env
  `UI_PROFILE` trước `streamlit run` — không hot-switch giữa phiên.

Profile (17/11):
- `b2_v52n` (MẶC ĐỊNH, cấu hình chính chốt 17/11): env `profiles/b2_v52n.json` (giống hệt env b2_v51a = env job API v52n đã kiểm),
  snapshot `runs/snapshots/20261117-b2-v52n`. Thêm KIỂM CODE: có tệp freeze của profile (`runs/freeze/20261117-v52n-ui/
  code_sha256.txt`) thì băm từng tệp; lệch → từ chối chạy, nhãn nêu số tệp lệch. Không có tệp freeze → nhãn ghi "chưa kiểm hash code".
- `b2_v51a` (quay lui / đối chiếu): nạp env của `profiles/b2_v51a.json` (bản sao env snapshot backend đã chọn; ARCH=target,
  PLANNER_VARIANT=b2_jev, DeepSeek / Jev thật, Qwen compose). Máy có snapshot `runs/snapshots/20261116-b2-v51A/config.json`
  thì đối chiếu thêm; lệch → từ chối chạy. Khởi động kiểm lại settings khớp profile.
  Cần key DeepSeek / TypeSafe trong môi trường (không hiện lên màn hình). Generator Qwen cần vLLM (QWEN_BASE_URL); không có
  thì đặt UI_QWEN=off: câu vẫn do code render từ block đã kiểm, phần compose của Qwen lùi về mặc định — UI ghi nhãn rõ
  "khác cấu hình đo" (không gọi đó là B2 như đo).
- `legacy_offline`: router rules + generator offline, pipeline cũ — CHỈ để xem giao diện / replay, nhãn rõ, không phải B2.

Câu trả lời UI hiện = câu backend gửi qua callback `on_emit` (đã qua guardrail, đúng lúc phát; không giả streaming).
Mỗi lượt có event_id: Streamlit rerun với cùng event_id trả lại kết quả cũ, không gọi model / tool ghi lần hai.
Feedback nhân viên (like/dislike theo message) và trace UI ghi vào data/ui/ (ngoài Git) — nguồn feedback 2 của C.5.
Gói FAQ C.5 đang kích hoạt (data/c5/active.json) chỉ được nạp khi MỞ phiên mới, không đổi giữa phiên.
"""
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

UI_DIR = os.environ.get("UI_DATA_DIR") or os.path.join(ROOT, "data", "ui")    # Kaggle: /kaggle/working/... (kaggle/ui_tunnel.py)
UI_DB = os.path.join(UI_DIR, "memory.db")
FEEDBACK = os.path.join(UI_DIR, "feedback.jsonl")
TRACES = os.path.join(UI_DIR, "traces")
C5_STATE = os.environ.get("C5_STATE_DIR") or os.path.join(ROOT, "data", "c5")
C5_ROOT = os.environ.get("C5_ROOT", os.path.join(ROOT, "runs", "c5", "review"))
# 17/11: profile B2 → (tệp profile trong Git, snapshot đã đo (runs/ ngoài Git), nhãn)
B2_PROFILES = {"b2_v52n": ("b2_v52n.json", "20261117-b2-v52n", "B2-v52n (cấu hình chính 17/11)"),
               "b2_v51a": ("b2_v51a.json", "20261116-b2-v51A", "B2-v51-A (snapshot đã chọn)")}
PROFILE = os.environ.get("UI_PROFILE", "b2_v52n")
_pf, _snap, _lab = B2_PROFILES.get(PROFILE, B2_PROFILES["b2_v52n"])
B2_PROFILE = os.path.join(ROOT, "profiles", _pf)                    # có trong Git → clone sạch chạy được
B2_SNAPSHOT = os.path.join(ROOT, "runs", "snapshots", _snap)        # chỉ có trên máy đã đo (runs/ ngoài Git)
B2_CONFIG = os.path.join(B2_SNAPSHOT, "config.json")
ASSERT_KEYS = ("ARCH", "PLANNER_VARIANT", "DEEPSEEK_MODEL", "DEEPSEEK_THINKING", "JEV_MODEL", "QWEN_MODEL", "PLANNER_SELECTOR",
               "PLANNER_B2_MAX_DECISIONS", "PLANNER_B2_MAX_TOOL_CALLS", "PLANNER_B2_DEADLINE_S", "GOAL_CONTRACT", "CONTRACT_V2")


def _apply_profile():
    """Đặt env của profile TRƯỚC khi core được import. → mô tả profile (hiện trên UI)."""
    os.environ.setdefault("RUN_PROFILE", "local")
    os.environ.setdefault("DATABASE_URL", "sqlite:///" + UI_DB.replace("\\", "/"))
    os.environ.setdefault("TOOL_TRANSPORT", "direct")
    os.environ.setdefault("RAG_MODE", "bm25")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if PROFILE == "legacy_offline":
        return {"profile": "legacy_offline", "label": "Pipeline cũ (rules + offline) — chỉ xem giao diện, KHÔNG phải B2",
                "router": "rules", "generator": "offline", "config_env": {}}
    if PROFILE not in B2_PROFILES:
        raise ValueError(f"UI_PROFILE={PROFILE!r} không hỗ trợ ({' | '.join(B2_PROFILES)} | legacy_offline)")
    prof = json.load(open(B2_PROFILE, encoding="utf-8"))
    env = {k: str(v) for k, v in (prof.get("env") or {}).items() if v is not None}
    drift = []
    if os.path.exists(B2_CONFIG):                            # đối chiếu profile (Git) với snapshot đã đo
        snap = {k: str(v) for k, v in (json.load(open(B2_CONFIG, encoding="utf-8")).get("env") or {}).items()
                if k not in ("ISO_TAG", "ISO_EXPECT")}
        drift = [k for k in set(snap) | set(env) if snap.get(k) != env.get(k)]
    for k in prof.get("runner_only") or ():
        env.pop(k, None)                                     # cờ của runner Kaggle, không thuộc agent
    env["IMPROVE_DIR"] = ""                                  # gói FAQ chỉ nạp khi mở phiên (Engine.start_call)
    for k, v in env.items():
        os.environ[k] = v
    qwen_off = os.environ.get("UI_QWEN", "on") == "off"
    code = code_check(prof.get("freeze"))
    name = _lab if PROFILE == "b2_v52n" else "B2-v51-A"
    label = (f"{_lab}, generator Qwen như cấu hình đo" if not qwen_off else
             f"{name}, KHÔNG có Qwen compose (UI_QWEN=off) — khác cấu hình đo, chỉ để demo")
    if code["status"] == "mismatch":
        label += f" — CẢNH BÁO: code lệch freeze {os.path.basename(code['freeze'])} ở {len(code['bad'])} tệp"
    elif code["status"] == "absent":
        label += " — chưa kiểm hash code (không có tệp freeze)"
    return {"profile": PROFILE, "snapshot": os.path.relpath(B2_SNAPSHOT, ROOT), "config_env": env, "profile_drift": sorted(drift),
            "profile_file": os.path.relpath(B2_PROFILE, ROOT), "freeze": prof.get("freeze"), "code": code,
            "router": "rules", "generator": "offline" if qwen_off else "qwen", "label": label}


def code_check(freeze):
    """17/11: băm code thực tế so với danh sách freeze của profile. → {"status": ok | mismatch | absent | none, "freeze", "checked",
    "bad": [tệp lệch / thiếu]}. Chỉ đọc."""
    import hashlib
    if not freeze:
        return {"status": "none", "freeze": None, "checked": 0, "bad": []}
    fl = os.path.join(ROOT, freeze, "code_sha256.txt")
    if not os.path.exists(fl):
        return {"status": "absent", "freeze": freeze, "checked": 0, "bad": []}
    bad, n = [], 0
    for ln in open(fl, encoding="utf-8"):
        if not ln.strip():
            continue
        h, f = ln.split(None, 1)
        f = f.strip().lstrip("*")
        p = os.path.join(ROOT, f)
        n += 1
        if not os.path.exists(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != h:
            bad.append(f)
    return {"status": "mismatch" if bad else "ok", "freeze": freeze, "checked": n, "bad": bad}


PROFILE_INFO = _apply_profile()

CHANNELS = ["hotline", "zalo_oa", "chat_fanpage"]

# Kịch bản demo C.6 (đề bài): cuộc 1 tư vấn + báo giá + KM, hẹn hỏi người nhà; cuộc 2 vài ngày sau chốt đơn;
# cuộc 3 (M2) gọi lại hỏi vận đơn. Lời khách viết tay cho demo, không lấy từ bộ test.
DEMO_PHONE = "0987650123"
DEMO_SCRIPT = [
    {"call": "call_1", "days_later": 0, "turns": [
        "Chào em, anh đang tìm máy lọc không khí cho phòng ngủ khoảng 30 mét vuông.",
        "Máy AirPure Y giá bao nhiêu em, có khuyến mãi gì không?",
        "Ừ để anh hỏi ý vợ đã rồi tính nhé, cuối tuần anh gọi lại.",
    ]},
    {"call": "call_2", "days_later": 3, "turns": [
        "Alo em, anh gọi lại vụ máy lọc không khí hôm trước.",
        "Nhà anh đồng ý rồi, em lên đơn cho anh nhé.",
        "Giao về số 12 Nguyễn Trãi, Thanh Xuân, Hà Nội giúp anh.",
    ]},
    {"call": "call_3", "days_later": 5, "turns": [
        "Em ơi đơn máy lọc không khí của anh giao tới đâu rồi?",
    ]},
]


def _imports():
    from core.llm.generator import Generator
    from core.llm.router import Router
    from harness.agent import CallSession
    from harness.memory import open_memory
    from harness.tools import ToolBox
    return Generator, Router, CallSession, open_memory, ToolBox


def startup_check():
    """Kiểm cấu hình thực tế so với config snapshot (profile B2). → {"ok", "mismatch", "label", ...}. Lệch → ok=False.
    b2_v52n: code lệch freeze của profile cũng là lệch (từ chối chạy); b2_v51a: chỉ cảnh báo trên nhãn (giữ hành vi cũ)."""
    from core.config import check_arch, settings
    info = {"profile": PROFILE_INFO["profile"], "label": PROFILE_INFO["label"], "arch": settings.arch,
            "planner_variant": settings.planner_variant, "mismatch": []}
    if PROFILE_INFO["profile"] not in B2_PROFILES:
        info["ok"] = False
        info["mismatch"].append("profile không phải B2 — chỉ xem giao diện")
        return info
    env = PROFILE_INFO["config_env"]
    if PROFILE_INFO.get("profile_drift"):
        info["mismatch"].append(f"{PROFILE_INFO['profile_file']} lệch snapshot ở {PROFILE_INFO['profile_drift']}")
    info["code"] = {k: PROFILE_INFO["code"][k] for k in ("status", "freeze", "checked")}
    if PROFILE_INFO["profile"] == "b2_v52n" and PROFILE_INFO["code"]["status"] == "mismatch":
        info["mismatch"].append(f"code lệch freeze {PROFILE_INFO['code']['freeze']}: {PROFILE_INFO['code']['bad'][:5]}")
    for k in ASSERT_KEYS:
        if k in env and os.environ.get(k) != env[k]:
            info["mismatch"].append(f"{k}: env {os.environ.get(k)!r} ≠ snapshot {env[k]!r}")
    if settings.arch != "target" or settings.planner_variant != "b2_jev":
        info["mismatch"].append(f"settings ARCH={settings.arch} PLANNER_VARIANT={settings.planner_variant} (cần target / b2_jev)")
    try:
        check_arch(settings)
    except ValueError as e:
        info["mismatch"].append(f"check_arch: {e}")
    info["keys_present"] = {k: bool(os.environ.get(k)) for k in ("DEEPSEEK_API_KEY", "TYPESAFE_API_KEY")}  # chỉ có/không, không giá trị
    info["ok"] = not info["mismatch"]
    return info


def active_package():
    p = os.path.join(C5_STATE, "active.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"package": "", "approved_hash": None}


def export_ui_data():
    """Gói dữ liệu UI để tải về (trước khi phiên Kaggle tắt): data UI (bộ nhớ, feedback, trace), trạng thái gói FAQ, kho duyệt C.5.
    Không gồm khóa API (khóa không nằm trong các thư mục này). → bytes của tệp zip."""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for tag, d in (("ui", UI_DIR), ("c5_state", C5_STATE), ("c5_review", C5_ROOT)):
            if not os.path.isdir(d):
                continue
            for dp, _, fs in os.walk(d):
                for f in fs:
                    p = os.path.join(dp, f)
                    z.write(p, os.path.join(tag, os.path.relpath(p, d)))
        z.writestr("EXPORT.json", json.dumps({"at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                              "profile": PROFILE_INFO.get("profile"), "dirs": {"ui": UI_DIR, "c5_state": C5_STATE,
                                                                                               "c5_review": C5_ROOT}}, ensure_ascii=False))
    return buf.getvalue()


def _append(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


class Engine:
    """Một "khách demo" = một namespace bộ nhớ. Mỗi cuộc gọi tạo một CallSession mới trên cùng namespace."""

    def __init__(self, name="demo", config="full", router=None, generator=None, start_date="2026-10-15"):
        Generator, Router, _, open_memory, ToolBox = _imports()
        self.name, self.config = name, config
        self.ns = f"ui:{PROFILE_INFO['profile']}:{config}:{name}"         # Full / Baseline / profile: namespace riêng
        self.mem = open_memory(self.ns, read_enabled=(config == "full"))
        self.router = Router(router or PROFILE_INFO["router"])
        self.gen = Generator(generator or PROFILE_INFO["generator"])
        self.start_date = start_date
        self.sess, self.calls, self.n_calls = None, [], 0
        self.events = {}                                         # event_id → row (chống gọi lại khi Streamlit rerun)
        self.emitted = []
        self.package = {"package": "", "approved_hash": None}
        self._ToolBox = ToolBox

    # ---------- vòng đời ----------
    def reset(self):
        """Xoá bộ nhớ của namespace này và trạng thái mock (đơn đã tạo, tồn kho)."""
        self.end_call()
        self.mem.wipe()
        self._ToolBox.reset_world()
        self.calls, self.n_calls, self.events = [], 0, {}

    def _on_emit(self, msg):
        self.emitted.append({**msg, "ui_received_at": time.time()})

    def _load_package(self):
        """Gói FAQ đang kích hoạt → IMPROVE_DIR cho phiên SẮP mở (không đổi giữa phiên)."""
        from core.config import settings
        from harness import improve_hook
        if self.sess is not None:
            raise RuntimeError("không đổi gói FAQ khi đang trong cuộc gọi")
        pkg = active_package() if PROFILE_INFO["profile"] in B2_PROFILES else {"package": "", "approved_hash": None}
        if settings.improve_dir != (pkg.get("package") or ""):
            settings.improve_dir = pkg.get("package") or ""
            improve_hook.reset()
        self.package = pkg

    def start_call(self, phone, channel="hotline", day=None, channel_identity=None, input_mode="text"):
        _, _, CallSession, _, _ = _imports()
        self.end_call()
        self._load_package()
        self.n_calls += 1
        day = day or self.start_date
        name = f"call_{self.n_calls}"
        self.sess = CallSession(memory=self.mem, today=day, call_name=name, session_id=f"{self.ns}:{name}",
                                channel=channel, channel_identity=channel_identity,
                                phone=phone if channel == "hotline" or not channel_identity else None,
                                input_mode=input_mode, router=self.router, generator=self.gen, config=self.config,
                                on_emit=self._on_emit)
        try:
            brief = self.sess.start()
        except Exception:
            self.sess = None                      # mở phiên lỗi (vd gói FAQ sai phạm vi) → không giữ phiên dở dang
            self.n_calls -= 1
            raise
        self.calls.append({"call": name, "date": day, "channel": channel, "brief": brief, "turns": [],
                           "session_id": f"{self.ns}:{name}", "package_hash": self.package.get("approved_hash")})
        return brief

    def say(self, text, event_id=None):
        """Một lượt. event_id đã xử lý → trả lại row cũ (không gọi model / tool lần hai)."""
        if event_id and event_id in self.events:
            return self.events[event_id]
        if self.sess is None:
            raise RuntimeError("chưa bắt đầu cuộc gọi")
        n0 = len(self.emitted)
        row = self.sess.turn(text)
        em = self.emitted[n0:]
        # row của CallSession.turn() không có trường "turn" (run_eval tự gắn khi ghi trace) → lấy số lượt từ message đã phát
        turn_no = em[-1].get("turn") if em else self.sess.turn_no
        row["ui"] = {"event_id": event_id, "emitted_text": em[-1].get("text") if em else None, "n_emit": len(em),
                     "session_id": self.calls[-1]["session_id"], "call": self.calls[-1]["call"], "turn": turn_no,
                     "msg_id": f"{self.calls[-1]['session_id']}:{turn_no}",
                     "package_hash": self.package.get("approved_hash"), "profile": PROFILE_INFO["profile"]}
        self.calls[-1]["turns"].append(row)
        if event_id:
            self.events[event_id] = row
        _append(os.path.join(TRACES, f"{self.ns.replace(':', '_')}.jsonl"),
                {**{k: row.get(k) for k in ("customer_text", "agent_text", "goals", "improve")},
                 "call": row["ui"]["call"], "turn": turn_no,
                 "session_id": row["ui"]["session_id"], "msg_id": row["ui"]["msg_id"], "ns": self.ns,
                 "package_hash": row["ui"]["package_hash"], "profile": PROFILE_INFO["profile"]})
        return row

    def end_call(self):
        if self.sess is not None:
            self.sess.end()                      # end() chờ audit nền xong rồi ghi phiên; câu đã phát hiển thị trước đó
            self.sess = None

    def feedback(self, row, rating, note="", by=""):
        """Like (+1) / dislike (-1) của nhân viên cho MỘT câu trả lời (theo msg_id) → data/ui/feedback.jsonl."""
        if rating not in (1, -1):
            raise ValueError("rating phải là 1 hoặc -1")
        ui = row.get("ui") or {}
        if not ui.get("msg_id") or ui.get("turn") is None:
            raise ValueError("câu trả lời không có msg_id / số lượt — không ghi feedback mồ côi")
        rec = {"msg_id": ui.get("msg_id"), "ns": self.ns, "session_id": ui.get("session_id"), "turn": ui.get("turn"),
               "rating": rating, "note": note, "by": by, "at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "config": self.config, "profile": PROFILE_INFO["profile"], "package_hash": ui.get("package_hash"),
               "customer_text": row.get("customer_text"), "agent_text": row.get("agent_text")}
        _append(FEEDBACK, rec)
        return rec

    # ---------- đọc bộ nhớ (chỉ đọc, thẳng từ DB) ----------
    def customer_id(self):
        if self.sess and self.sess.customer:
            return self.sess.customer["customer_id"]
        for c in reversed(self.calls):
            cid = (c["brief"] or {}).get("customer_phone")
            if cid:
                ids = self.mem.lookup("phone", cid)
                if ids:
                    return ids[0]
        return None

    def timeline(self, customer_id=None):
        """Dòng thời gian bộ nhớ: phiên + fact (kể cả fact đã bị thay thế, có nguồn) + báo giá + kết quả hành động, theo ngày."""
        from sqlalchemy import and_, select
        from harness import memory as M
        cid = customer_id or self.customer_id()
        if not cid or not hasattr(self.mem, "e"):
            return []
        ev = []
        with self.mem.e.connect() as c:
            for r in c.execute(select(M.sessions).where(and_(M.sessions.c.ns == self.ns, M.sessions.c.customer_id == cid))).mappings():
                ev.append({"date": r["started_on"], "kind": "phiên", "what": f"{r['session_id']} · {r['channel']} · {r['outcome']}",
                           "detail": r["summary"], "source": r["source"], "status": ""})
            for r in c.execute(select(M.facts).where(and_(M.facts.c.ns == self.ns, M.facts.c.customer_id == cid))
                               .order_by(M.facts.c.fact_id)).mappings():
                ev.append({"date": r["valid_from"], "kind": "fact", "what": r["slot"],
                           "detail": json.loads(r["value_json"]), "source": r["source"],
                           "status": r["status"] + (f" → #{r['superseded_by']}" if r["superseded_by"] else "")
                           + f" · hết hạn {r['expires_on']}", "fact_id": r["fact_id"]})
            for r in c.execute(select(M.quotes).where(and_(M.quotes.c.ns == self.ns, M.quotes.c.customer_id == cid))
                               .order_by(M.quotes.c.quote_id)).mappings():
                ev.append({"date": r["quoted_on"], "kind": "báo giá", "what": f"{r['sku']} ({r['role']})",
                           "detail": {"giá": r["final_price_vnd"], "KM": r["promo_code"], "KM hết hạn": r["promo_end"]},
                           "source": r["session_id"], "status": ""})
        for c in self.calls:                                   # kết quả hành động (tool ghi thành công) của các cuộc trong UI
            for row in c["turns"]:
                for t in row.get("tool_calls") or []:
                    if t["name"] in ("order.create", "order.update", "schedule.callback", "handoff.transfer"):
                        res = t.get("result") or {}
                        ev.append({"date": c["date"], "kind": "hành động", "what": t["name"],
                                   "detail": {k: res.get(k) for k in ("order_id", "status", "action", "ticket_id", "callback_at") if res.get(k)},
                                   "source": f"{c['call']} lượt {(row.get('ui') or {}).get('turn')}", "status": "lỗi" if res.get("error") else "ok"})
        order = {"phiên": 0, "báo giá": 1, "fact": 2, "hành động": 3}
        return sorted(ev, key=lambda e: (e["date"] or "", order[e["kind"]]))

    # ---------- demo C.6 ----------
    def run_demo(self, upto=None, phone=DEMO_PHONE):
        """Chạy kịch bản C.6 từ đầu (reset trước). `upto` = số cuộc gọi muốn chạy (mặc định tất cả)."""
        self.reset()
        d0 = date.fromisoformat(self.start_date)
        for c in DEMO_SCRIPT[:upto]:
            self.start_call(phone, "hotline", (d0 + timedelta(days=c["days_later"])).isoformat())
            for i, t in enumerate(c["turns"]):
                self.say(t, event_id=f"demo:{c['call']}:{i}")
            self.end_call()
        return self.calls


# ---------- chỉ số: chỉ đọc report có nhãn phiên bản rõ ----------
LABELED_REPORTS = [
    {"label": "dev92 · B2-v50 (dev50-full/base-1116) — số của v50, KHÔNG phải v51-A",
     "path": "runs/kaggle/dev50-score-1116/out/dev50-score-1116/report.json", "version": "v50", "dataset": "dev92 (registry dev)",
     "backend": "DeepSeek v4 flash + Jev + Qwen3-4B (thật)", "measured": "2026-11-16"},
]


def reports(base=os.path.join(ROOT, "runs")):
    """Report có nhãn (phiên bản / bộ dữ liệu / backend / ngày) trước, rồi các report.json khác dưới runs/ (nhãn 'chưa gắn')."""
    out = [dict(r, path=os.path.join(ROOT, r["path"])) for r in LABELED_REPORTS if os.path.exists(os.path.join(ROOT, r["path"]))]
    known = {r["path"] for r in out}
    for d, _, fs in os.walk(base):
        for f in fs:
            p = os.path.join(d, f)
            if (f == "report.json" or f.endswith(".report.json")) and p not in known:
                out.append({"label": f"chưa gắn nhãn: {os.path.relpath(p, ROOT)}", "path": p, "version": "?", "dataset": "?",
                            "backend": "?", "measured": "?"})
    return out


METRIC_ROWS = [("Repeat-Question Rate (%)", "repeat_question_rate", "value"),
               ("Context Carryover Rate (%)", "context_carryover_rate", "value"),
               ("Task Success Rate (%)", "task_success_rate", "value"),
               ("Hallucination giá & KM (%)", "hallucination_rate", "price_promo_only.value"),
               ("Số lượt TB / cuộc", "avg_turns_per_call", None),
               ("Vi phạm guardrail", "guardrail_violations", "total")]


def _dig(d, path):
    for k in (path or "").split(".") if path else []:
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return d


def metric_table(report):
    """→ [(tên chỉ số, baseline, hệ thống)] từ report.json của eval/reference_eval.py."""
    rows = []
    for title, key, path in METRIC_ROWS:
        vals = []
        for side in ("baseline", "system"):
            v = (report.get(side) or {}).get(key)
            v = _dig(v, path) if path else (v.get("value") if isinstance(v, dict) else v)
            vals.append(v)
        rows.append((title, *vals))
    return rows
