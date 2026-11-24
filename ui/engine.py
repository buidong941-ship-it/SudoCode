"""Lớp chạy agent cho UI — gọi core đúng như `run_eval.py`, không sửa core, không dùng chung DB với lần chạy đo.

Tách biệt:
- core (harness/, core/, eval/) không import ui/ (tests/ui_check.py kiểm tra);
- UI có DB bộ nhớ riêng `data/ui/memory.db` và namespace riêng `ui:<config>:<tên demo>`, nên không đụng DB / namespace đo;
- env phải đặt TRƯỚC khi import harness (settings đọc env lúc import): profile được chọn MỘT LẦN cho cả tiến trình qua env
  `UI_PROFILE` trước `streamlit run` — không hot-switch giữa phiên.

Profile (17/11):
- `b2_v52n` (MẶC ĐỊNH, cấu hình chính chốt 17/11): env `profiles/b2_v52n.json` (giống hệt env b2_v51a = env job API v52n đã kiểm),
  snapshot `runs/snapshots/20261117-b2-v52n`. Thêm KIỂM CODE: có tệp freeze của profile (`runs/freeze/20261117-v52n-ui2/
  code_sha256.txt`; bản trước v52n-ui) thì băm từng tệp; lệch → từ chối chạy, nhãn nêu số tệp lệch. Không có tệp freeze → nhãn ghi "chưa kiểm hash code".
- `b2_v51a` (quay lui / đối chiếu): nạp env của `profiles/b2_v51a.json` (bản sao env snapshot backend đã chọn; ARCH=target,
  PLANNER_VARIANT=b2_jev, DeepSeek / Jev thật, Qwen compose). Máy có snapshot `runs/snapshots/20261116-b2-v51A/config.json`
  thì đối chiếu thêm; lệch → từ chối chạy. Khởi động kiểm lại settings khớp profile.
  Cần key DeepSeek / TypeSafe trong môi trường (không hiện lên màn hình). Generator Qwen cần vLLM (QWEN_BASE_URL); không có
  thì đặt UI_QWEN=off: câu vẫn do code render từ block đã kiểm, phần compose của Qwen lùi về mặc định — UI ghi nhãn rõ
  "khác cấu hình đo" (không gọi đó là B2 như đo).
- `legacy_offline`: router rules + generator offline, pipeline cũ — CHỈ để xem giao diện / replay, nhãn rõ, không phải B2.
- `b2_integ_tt` (CANDIDATE tích hợp B2-TT + hướng dẫn điều phối, freeze `runs/freeze/20261117-integ-ui`; không phải bản chính):
  hai cờ độc lập chọn trên thanh bên, áp dụng khi MỞ cuộc gọi (B2_TWO_TIER; dùng gói hướng dẫn đang kích hoạt). Gói FAQ không nạp
  (R0 / R1 chỉ khác gói hướng dẫn). Kho duyệt hướng dẫn GUIDE_ROOT, gói GUIDE_PKG_DIR, trạng thái kích hoạt GUIDE_STATE_DIR.
  18/11 (freeze `runs/freeze/20261118-integ-ui3`): sửa nháp thành phiên bản mới (improve/guidance_edit.py) và so sánh trước / sau
  với Jev thật trong tiến trình thử riêng (`sandbox_*`, scripts/guidance_sandbox.py) — kết quả thử lưu ở GUIDE_ROOT/sandbox/.

Câu trả lời UI hiện = câu backend gửi qua callback `on_emit` (đã qua guardrail, đúng lúc phát; không giả streaming).
Mỗi lượt có event_id: Streamlit rerun với cùng event_id trả lại kết quả cũ, không gọi model / tool ghi lần hai.
Feedback nhân viên (like/dislike theo message) và trace UI ghi vào data/ui/ (ngoài Git) — nguồn feedback 2 của C.5.
17/11 (v52n-ui2): tab Cải tiến gọi `c5_loop.py gaps` trên feedback + trace UI (`gap_cmd`) và `c5_loop.py draft` (`draft_cmd`),
nên dislike trên UI thực sự đi vào vòng gap → nháp FAQ → duyệt. Số cuộc gọi lấy từ DB (`_next_call_no`): tải lại trang không
còn trùng session_id / msg_id.
Gói FAQ C.5 đang kích hoạt (data/c5/active.json) chỉ được nạp khi MỞ phiên mới, không đổi giữa phiên.
"""
import hashlib
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
_UI_DATA = os.environ.get("UI_DATA_DIR")                            # Kaggle: dữ liệu duyệt / gói nằm cạnh dữ liệu UI để tải về được
GUIDE_ROOT = os.environ.get("GUIDE_ROOT") or (os.path.join(_UI_DATA, "guidance_review") if _UI_DATA
                                              else os.path.join(ROOT, "runs", "c5", "guidance_review"))
GUIDE_PKGS = os.environ.get("GUIDE_PKG_DIR") or (os.path.join(_UI_DATA, "guidance_packages") if _UI_DATA
                                                 else os.path.join(ROOT, "runs", "c5", "guidance_packages"))
GUIDE_STATE = os.environ.get("GUIDE_STATE_DIR") or (os.path.join(_UI_DATA, "guidance_state") if _UI_DATA
                                                    else os.path.join(ROOT, "data", "c5", "guidance"))
GUIDE_LOOP = os.path.join(ROOT, "scripts", "guidance_loop.py")
# 17/11: profile B2 → (tệp profile trong Git, snapshot đã đo (runs/ ngoài Git) hoặc None, nhãn)
B2_PROFILES = {"b2_v52n": ("b2_v52n.json", "20261117-b2-v52n", "B2-v52n (cấu hình chính 17/11)"),
               "b2_v51a": ("b2_v51a.json", "20261116-b2-v51A", "B2-v51-A (snapshot đã chọn)"),
               "b2_integ_tt": ("b2_integ_tt.json", None, "Candidate tích hợp B2-TT + hướng dẫn (thử nghiệm, không phải bản chính)")}
CANDIDATE_PROFILES = ("b2_integ_tt",)
PROFILE = os.environ.get("UI_PROFILE", "b2_v52n")
CANDIDATE = PROFILE in CANDIDATE_PROFILES
_pf, _snap, _lab = B2_PROFILES.get(PROFILE, B2_PROFILES["b2_v52n"])
B2_PROFILE = os.path.join(ROOT, "profiles", _pf)                    # có trong Git → clone sạch chạy được
B2_SNAPSHOT = os.path.join(ROOT, "runs", "snapshots", _snap) if _snap else None   # chỉ có trên máy đã đo (runs/ ngoài Git)
B2_CONFIG = os.path.join(B2_SNAPSHOT, "config.json") if B2_SNAPSHOT else None
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
    if B2_CONFIG and os.path.exists(B2_CONFIG):              # đối chiếu profile (Git) với snapshot đã đo
        snap = {k: str(v) for k, v in (json.load(open(B2_CONFIG, encoding="utf-8")).get("env") or {}).items()
                if k not in ("ISO_TAG", "ISO_EXPECT")}
        drift = [k for k in set(snap) | set(env) if snap.get(k) != env.get(k)]
    for k in prof.get("runner_only") or ():
        env.pop(k, None)                                     # cờ của runner Kaggle, không thuộc agent
    env["IMPROVE_DIR"] = ""                                  # gói FAQ chỉ nạp khi mở phiên (Engine.start_call)
    if CANDIDATE:
        env["PLANNER_GUIDANCE_DIR"] = ""                     # gói hướng dẫn chỉ nạp khi mở phiên (Engine._load_mode)
    for k, v in env.items():
        os.environ[k] = v
    qwen_off = os.environ.get("UI_QWEN", "on") == "off"
    code = code_check(prof.get("freeze"))
    name = "B2-v51-A" if PROFILE == "b2_v51a" else _lab
    label = (f"{_lab}, generator Qwen như cấu hình đo" if not qwen_off else
             f"{name}, KHÔNG có Qwen compose (UI_QWEN=off) — khác cấu hình đo, chỉ để demo")
    if code["status"] == "mismatch":
        label += f" — CẢNH BÁO: code lệch freeze {os.path.basename(code['freeze'])} ở {len(code['bad'])} tệp"
    elif code["status"] == "absent":
        label += " — chưa kiểm hash code (không có tệp freeze)"
    return {"profile": PROFILE, "snapshot": os.path.relpath(B2_SNAPSHOT, ROOT) if B2_SNAPSHOT else None, "config_env": env,
            "profile_drift": sorted(drift), "candidate": CANDIDATE,
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
    if PROFILE_INFO["profile"] in ("b2_v52n", *CANDIDATE_PROFILES) and PROFILE_INFO["code"]["status"] == "mismatch":
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


# ---------- 17/11 candidate: kho hướng dẫn điều phối (chỉ profile candidate) ----------
GUIDE_KEYS = ("guide_id", "version", "title", "audience", "tags", "applies_when", "exceptions", "guidance", "avoid", "examples",
              "counterexamples", "requires_capabilities", "conflict_group", "asks_any")
MODE_LABEL = {"off": "đối chứng (hai cờ tắt)", "tt": "nền B2-TT", "g": "chỉ hướng dẫn (một tầng)", "ttg": "B2-TT + hướng dẫn"}


def mode_code(two_tier, guidance_on):
    return {(False, False): "off", (True, False): "tt", (False, True): "g", (True, True): "ttg"}[(bool(two_tier), bool(guidance_on))]


def guidance_active():
    p = os.path.join(GUIDE_STATE, "active.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"package": "", "approved_hash": None}


def guidance_cmd(*args):
    """argv `scripts/guidance_loop.py <args>` (import / package / regress / activate / rollback)."""
    return [sys.executable, GUIDE_LOOP, *args]


def guidance_props(state):
    from improve import store as S
    return [p for p in S.list_state(state, GUIDE_ROOT) if p.get("kind") == "planner_guidance"]


def guide_dto(prop):
    """Đề xuất trong kho → dạng hướng dẫn mà harness.guidance dùng (giống improve_hook.guidance_package)."""
    return {"id": prop["id"], **{k: prop["payload"][k] for k in GUIDE_KEYS if prop["payload"].get(k) is not None}}


def guidance_packages():
    """Gói đã đóng dưới GUIDE_PKGS → [{"name", "path", "meta"}] (mới nhất trước)."""
    if not os.path.isdir(GUIDE_PKGS):
        return []
    out = []
    for n in sorted(os.listdir(GUIDE_PKGS), reverse=True):
        pj = os.path.join(GUIDE_PKGS, n, "PACKAGE.json")
        if os.path.exists(pj):
            out.append({"name": n, "path": os.path.join(GUIDE_PKGS, n), "meta": json.load(open(pj, encoding="utf-8"))})
    return out


def package_guides(path):
    from harness import improve_hook
    return list(improve_hook.guidance_package(path)["guides"])


def guidance_evidence(refs):
    """Hồ sơ bằng chứng LOCAL (evidence.jsonl cạnh kho; có ID kịch bản, không bao giờ vào gói / prompt). Không có tệp → []."""
    p = os.path.join(GUIDE_ROOT, "evidence.jsonl")
    if not refs or not os.path.exists(p):
        return []
    want = set(refs)
    return [r for r in (json.loads(l) for l in open(p, encoding="utf-8") if l.strip()) if r.get("ev") in want]


def guide_capabilities():
    from harness import guidance as G
    return {"one_tier": set(G.BASE_CAPS), "two_tier": set(G.BASE_CAPS) | set(G.TT_CAPS)}


def try_retrieval(guides, text, asked_slot=None, asks=(), two_tier=True, consult=None):
    """Truy hồi THẬT (harness.guidance.for_turn) trên một tập hướng dẫn, ngoài cuộc gọi — chỉ đọc, không mở phiên, không gọi model.
    Đổi tạm settings.b2_two_tier để lọc năng lực đúng chế độ rồi trả lại. → {"selected": [...], "trace": {...}}."""
    import hashlib
    from types import SimpleNamespace
    from core.config import settings
    from harness import guidance as G
    body = json.dumps(list(guides), ensure_ascii=False, sort_keys=True)
    pin = {"hash": "preview-" + hashlib.sha256(body.encode()).hexdigest()[:16], "guides": tuple(guides)}
    st = SimpleNamespace(guidance_pin=pin, u_turn={"asks": list(asks or []), "consult": consult or {}}, last_q_slot=asked_slot or None,
                         b2tt_task=None, history=[])
    old = settings.b2_two_tier
    settings.b2_two_tier = bool(two_tier)
    try:
        return G.for_turn(SimpleNamespace(s=st, text=text or ""))
    finally:
        settings.b2_two_tier = old


def run_guide_tests(target_id, guides, tests):
    """Chạy test dữ liệu của MỘT hướng dẫn trên cả tập `guides` (để thấy cả hướng dẫn khác chen vào). Giống guidance_loop regress."""
    out = []
    for tc in tests or []:
        r = try_retrieval(guides, tc.get("customer_text"), tc.get("asked_slot"), tc.get("asks") or (), bool(tc.get("two_tier")),
                          tc.get("consult"))
        sel = r["trace"].get("selected") or []
        hit = target_id in sel
        out.append({"test": tc.get("name"), "expect": tc.get("expect"), "selected": hit,
                    "pass": hit == (tc.get("expect") == "selected"), "chosen": sel,
                    "scores": {c["id"]: c["score"] for c in r["trace"].get("candidates") or []}})
    return out


# ---------- 18/11 candidate: so sánh trước / sau với Jev thật (tiến trình thử riêng: scripts/guidance_sandbox.py) ----------
SANDBOX_SCRIPT = os.path.join(ROOT, "scripts", "guidance_sandbox.py")
SANDBOX_TIMEOUT_S = 1500


def payload_sha(prop):
    return hashlib.sha256(json.dumps(prop.get("payload") or {}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def sandbox_dir(pid):
    """Kết quả thử của một bản nháp (hồ sơ duyệt local, cạnh kho; đi kèm ui_data.zip). Không phải gói, agent không nạp."""
    return os.path.join(GUIDE_ROOT, "sandbox", pid)


def sandbox_spec(prop, base, trials, context=(), two_tier=True, by="", day=None, phone="0900111222", channel="hotline"):
    """base: "empty" (trước = không hướng dẫn, như R0) | "approved" (trước = các hướng dẫn đã duyệt hiện tại)."""
    if base not in ("empty", "approved"):
        raise ValueError("base phải là empty | approved")
    return {"draft": guide_dto(prop), "draft_prop": prop["id"], "draft_payload_sha": payload_sha(prop), "base": base,
            "base_guides": [] if base == "empty" else [guide_dto(p) for p in guidance_props("approved")],
            "trials": [t.strip() for t in trials if t and t.strip()], "context": [c for c in context if c and c.strip()],
            "two_tier": bool(two_tier), "by": by, "day": day, "phone": phone, "channel": channel}


def sandbox_run(spec, timeout=SANDBOX_TIMEOUT_S):
    """Chạy phiên thử ở TIẾN TRÌNH RIÊNG (DB / mock / trace riêng; settings của UI không đổi). → (rc, log, result | None, out)."""
    import secrets
    import subprocess
    out = os.path.join(sandbox_dir(spec["draft_prop"]), datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2))
    os.makedirs(out, exist_ok=True)
    sp = os.path.join(out, "spec.json")
    with open(sp, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=1)
    try:
        r = subprocess.run([sys.executable, SANDBOX_SCRIPT, "--spec", sp, "--out", out], capture_output=True, text=True, timeout=timeout,
                           cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        rc, log = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        rc, log = 124, f"quá {timeout} s — dừng phiên thử"
    rp = os.path.join(out, "result.json")
    res = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else None
    return rc, log[-3000:], res, out


def sandbox_history(pid):
    """Các lần thử đã lưu của một bản nháp (mới nhất trước) → [result]."""
    d = sandbox_dir(pid)
    if not os.path.isdir(d):
        return []
    out = []
    for n in sorted(os.listdir(d), reverse=True):
        rp = os.path.join(d, n, "result.json")
        if os.path.exists(rp):
            out.append({**json.load(open(rp, encoding="utf-8")), "_dir": n})
    return out


def sandbox_contexts():
    """Cuộc gọi đã có trên UI (trace UI) → {session_id: [(lượt, lời khách)]} để chọn ngữ cảnh phát lại trong phiên thử."""
    out = {}
    for f in ui_traces():
        for l in open(f, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                if r.get("session_id") and r.get("customer_text"):
                    out.setdefault(r["session_id"], []).append((r.get("turn"), r["customer_text"]))
    return {k: sorted(v, key=lambda x: (x[0] is None, x[0])) for k, v in out.items()}


def export_ui_data():
    """Gói dữ liệu UI để tải về (trước khi phiên Kaggle tắt): data UI (bộ nhớ, feedback, trace), trạng thái gói FAQ, kho duyệt C.5.
    Không gồm khóa API (khóa không nằm trong các thư mục này). → bytes của tệp zip."""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        dirs = [("ui", UI_DIR), ("c5_state", C5_STATE), ("c5_review", C5_ROOT)]
        if CANDIDATE:
            dirs += [("guidance_review", GUIDE_ROOT), ("guidance_packages", GUIDE_PKGS), ("guidance_state", GUIDE_STATE)]
        for tag, d in dirs:
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


C5_LOOP = os.path.join(ROOT, "scripts", "c5_loop.py")


def ui_traces():
    import glob
    return sorted(glob.glob(os.path.join(TRACES, "*.jsonl")))


def gap_cmd(root=None, trace=None, report=None):
    """17/11 (v52n-ui2): argv `c5_loop.py gaps` cho nút "Gom gap" ở tab Cải tiến — nguồn 2 (like/dislike nhân viên, khớp msg_id với
    trace UI) và tùy chọn nguồn 1 (trace + report dev của bộ đánh giá). --append: gap đã có id thì bỏ qua, không mất gap cũ."""
    cmd = [sys.executable, C5_LOOP, "gaps", "--root", root or C5_ROOT, "--feedback", FEEDBACK, "--append"]
    if trace:
        cmd += ["--trace", trace] + (["--report", report] if report else [])
    tr = ui_traces()
    if tr:
        cmd += ["--ui-trace", *tr]
    return cmd


def draft_cmd(root=None, types=None, limit=20):
    """argv `c5_loop.py draft` (DeepSeek soạn NHÁP vào pending/; gap đã có đề xuất hoặc đã kết luận thì bỏ qua)."""
    cmd = [sys.executable, C5_LOOP, "draft", "--root", root or C5_ROOT, "--limit", str(int(limit))]
    if types:
        cmd += ["--types", ",".join(types)]
    return cmd


def gap_counts(gaps):
    """{"nguồn:loại": số} — đếm thật (bản cũ ở tab Cải tiến luôn ra 0)."""
    out = {}
    for g in gaps:
        k = f"{g.get('feedback_source')}:{g.get('type')}"
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


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
        # candidate: hai cờ độc lập, áp dụng cho cuộc gọi MỞ SAU (mặc định = profile: B2-TT bật, dùng gói đang kích hoạt nếu có)
        self.two_tier = CANDIDATE and os.environ.get("B2_TWO_TIER") == "1"
        self.use_guidance = CANDIDATE
        self.guidance = {"package": "", "approved_hash": None}

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
        on = PROFILE_INFO["profile"] in B2_PROFILES and not CANDIDATE          # candidate: không nạp FAQ (R0 / R1 chỉ khác gói hướng dẫn)
        pkg = active_package() if on else {"package": "", "approved_hash": None}
        if settings.improve_dir != (pkg.get("package") or ""):
            settings.improve_dir = pkg.get("package") or ""
            improve_hook.reset()
        self.package = pkg

    def _load_mode(self):
        """Candidate: hai cờ (B2_TWO_TIER, dùng gói hướng dẫn đang kích hoạt) → settings cho phiên SẮP mở. Gói được CallSession.start()
        khóa lại (harness.guidance.pin); gói sai → GuidanceScopeError, phiên không mở. Không đổi giữa phiên."""
        if not CANDIDATE:
            return
        from core.config import check_arch, settings
        if self.sess is not None:
            raise RuntimeError("không đổi chế độ / gói hướng dẫn khi đang trong cuộc gọi")
        g = guidance_active() if self.use_guidance else {"package": "", "approved_hash": None}
        settings.b2_two_tier = bool(self.two_tier)
        settings.planner_guidance_dir = g.get("package") or ""
        check_arch(settings)
        self.guidance = g

    def mode(self):
        """Chế độ của cuộc gọi đang mở (theo gói thật sự đã khóa), hoặc chế độ sẽ áp dụng cho cuộc gọi mở sau."""
        if self.sess is not None:
            return mode_code(getattr(self.sess, "_ui_two_tier", False), getattr(self.sess, "guidance_pin", None))
        return mode_code(self.two_tier, self.use_guidance and guidance_active().get("package"))

    def _next_call_no(self):
        """17/11 (v52n-ui2): số cuộc gọi kế tiếp lấy từ DB của namespace, không chỉ từ bộ đếm trong RAM.

        Engine sống trong st.session_state (theo phiên trình duyệt), còn DB UI nằm trên đĩa: tải lại trang / tunnel nối lại tạo
        Engine mới với n_calls = 0 → `call_1` trùng session_id cũ → UNIQUE(turns.ns, session_id, turn) khi ghi lượt, và msg_id
        của feedback trùng giữa hai lần. Lấy max(số call_N đã có trong sessions + turns, bộ đếm RAM) + 1."""
        from sqlalchemy import select
        from harness import memory as M
        e = getattr(self.mem, "e", None) or M.engine()
        pre, used = f"{self.ns}:call_", {self.n_calls}
        with e.connect() as c:
            for t in (M.sessions, M.turns):
                for sid in c.execute(select(t.c.session_id).where(t.c.ns == self.ns)).scalars():
                    tail = sid[len(pre):] if sid and sid.startswith(pre) else ""
                    if tail.isdigit():
                        used.add(int(tail))
        return max(used) + 1

    def start_call(self, phone, channel="hotline", day=None, channel_identity=None, input_mode="text"):
        _, _, CallSession, _, _ = _imports()
        self.end_call()
        self._load_package()
        self._load_mode()
        prev_n = self.n_calls
        self.n_calls = self._next_call_no()
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
            self.sess = None                      # mở phiên lỗi (vd gói FAQ / gói hướng dẫn sai) → không giữ phiên dở dang
            self.n_calls = prev_n
            raise
        pin = getattr(self.sess, "guidance_pin", None) if CANDIDATE else None
        self.sess._ui_two_tier = bool(CANDIDATE and self.two_tier)
        self.calls.append({"call": name, "date": day, "channel": channel, "brief": brief, "turns": [],
                           "session_id": f"{self.ns}:{name}", "package_hash": self.package.get("approved_hash"),
                           "mode": self.mode() if CANDIDATE else None, "guidance_hash": (pin or {}).get("hash"),
                           "guidance_name": (pin or {}).get("name")})
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
                     "package_hash": self.package.get("approved_hash"), "profile": PROFILE_INFO["profile"],
                     "mode": self.calls[-1].get("mode"), "guidance_hash": self.calls[-1].get("guidance_hash")}
        self.calls[-1]["turns"].append(row)
        if event_id:
            self.events[event_id] = row
        loop = (row.get("planner") or {}).get("loop") or {}
        _append(os.path.join(TRACES, f"{self.ns.replace(':', '_')}.jsonl"),
                {**{k: row.get(k) for k in ("customer_text", "agent_text", "goals", "improve")},
                 "call": row["ui"]["call"], "turn": turn_no,
                 "session_id": row["ui"]["session_id"], "msg_id": row["ui"]["msg_id"], "ns": self.ns,
                 "package_hash": row["ui"]["package_hash"], "profile": PROFILE_INFO["profile"],
                 "mode": row["ui"]["mode"], "guidance_hash": row["ui"]["guidance_hash"], "guidance": loop.get("guidance"),
                 "two_tier": {k: (loop.get("two_tier") or {}).get(k) for k in ("task", "outcome")} if loop.get("two_tier") else None})
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
               "mode": ui.get("mode"), "guidance_hash": ui.get("guidance_hash"),
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
