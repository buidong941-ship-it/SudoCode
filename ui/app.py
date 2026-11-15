"""Giao diện demo (plan 01/11 mục F, đề bài C.6) — Streamlit, TÁCH BIỆT với core.

    pip install -r requirements-ui.txt
    streamlit run ui/app.py

Tab:
- Cuộc gọi     khung chat; Call Brief hiện khi khách gọi lại; chi tiết từng lượt (goal, tool, guardrail, claim);
               cảnh báo khi agent sắp cam kết sai (bản nháp bị guardrail chặn, câu có cụm cam kết) — đề C.6 mức M2
- Demo C.6     chạy lần lượt cuộc 1 (tư vấn, báo giá + KM, hẹn hỏi người nhà) → cuộc 2 (chốt đơn) → cuộc 3 (hỏi vận đơn)
- Bộ nhớ       dòng thời gian của khách: phiên, báo giá, fact (kể cả fact đã bị thay thế, có nguồn)
- Chỉ số       bảng full so với baseline từ report.json của eval/reference_eval.py
- Cải tiến     duyệt đề xuất của improve/ (pending → approved / rejected), xem các vòng

UI dùng DB bộ nhớ riêng (data/ui/memory.db) và namespace `ui:*`, xem ui/engine.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from ui import engine as E  # noqa: E402  (đặt env cho core trước khi core được import)
from improve.store import PROMISE_RX  # noqa: E402  (cùng định nghĩa câu hứa với Exemplar Bank)

st.set_page_config(page_title="SUDO CODE · Telesale agent", layout="wide")

# ---------- CSS — Sudo Code brand theme ----------
# Palette: deep navy bg · cyan-teal accent · purple secondary · white text
st.markdown("""
<style>
/* ── Google Fonts & Material Symbols ── */
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700;800&family=Space+Mono:wght@400;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons+Round');

/* ═══════════════════════════════════════════════════
   SUDO CODE BRAND THEME
   bg        #09090f  (deep space navy)
   surface   #0f1117  (cards / sidebar)
   surface2  #161b2e  (elevated surfaces)
   border    #1e2235  (subtle border)
   accent    #00d4ff  (cyan primary)
   accent2   #7c3aed  (purple secondary)
   text      #ffffff
   text-muted #94a3b8
   ═══════════════════════════════════════════════════ */

/* ── Global background ── */
.stApp {
    background-color: #09090f;
}
.stMainBlockContainer {
    background-color: #09090f;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background-color: #0c0e18 !important;
    border-right: 1px solid #1e2235;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    font-size: 15px !important;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: #ffffff;
    font-family: monospace;
}
/* namespace/DB badge */
section[data-testid="stSidebar"] .stCaption p {
    background: #0f1117;
    border: 1px solid #1e2235;
    border-radius: 6px;
    padding: 6px 10px;
    font-family: monospace;
    font-size: 11px;
    color: #00d4ff;
    line-height: 1.6;
}
/* Nút Xoá bộ nhớ — cyan outline */
section[data-testid="stSidebar"] .stButton > button {
    border-color: #00d4ff !important;
    color: #00d4ff !important;
    border-radius: 8px;
    font-size: 13px;
    background: transparent !important;
    transition: background 0.15s, box-shadow 0.15s;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #00d4ff18 !important;
    box-shadow: 0 0 10px #00d4ff33;
}

/* ── Tab bar ── */
button[data-baseweb="tab"] {
    font-size: 14px;
    letter-spacing: 0.3px;
    padding-bottom: 8px !important;
    color: #94a3b8;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #00d4ff !important;
    border-bottom: 2px solid #00d4ff !important;
    font-weight: 700;
    text-shadow: 0 0 8px #00d4ff66;
}
button[data-baseweb="tab"]:hover {
    color: #e2e8f0 !important;
}

/* ── Input / Select ── */
input, textarea, [data-testid="stDateInput"] input {
    border-radius: 8px !important;
    border: 1px solid #1e2235 !important;
    background: #0f1117 !important;
    color: #ffffff !important;
    transition: border-color 0.2s, box-shadow 0.2s;
}
input:focus, textarea:focus {
    border-color: #00d4ff !important;
    box-shadow: 0 0 0 2px #00d4ff28, 0 0 12px #00d4ff18 !important;
}
/* Select box */
[data-testid="stSelectbox"] > div > div {
    border-radius: 8px !important;
    border: 1px solid #1e2235 !important;
    background: #0f1117 !important;
}
/* Widget labels — small caps muted */
label[data-testid="stWidgetLabel"] > p,
label[data-testid="stWidgetLabel"] > div > p {
    font-size: 11px !important;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94a3b8 !important;
}

/* ── Primary button — cyan glow ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0ea5e9, #00d4ff) !important;
    border: none !important;
    border-radius: 8px !important;
    color: #000000 !important;
    font-weight: 700;
    letter-spacing: 0.3px;
    box-shadow: 0 2px 12px #00d4ff44;
    transition: transform 0.1s, box-shadow 0.15s;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 20px #00d4ff66 !important;
}
.stButton > button[kind="primary"]:active {
    transform: translateY(0);
}

/* ── Secondary button — white outline ── */
.stMainBlockContainer .stButton > button[kind="secondary"] {
    border-radius: 8px !important;
    border: 1px solid #ffffff44 !important;
    color: #ffffff !important;
    background: transparent !important;
    transition: border-color 0.15s, background 0.15s;
}
.stMainBlockContainer .stButton > button[kind="secondary"]:hover {
    border-color: #00d4ff !important;
    background: #00d4ff0f !important;
}

/* ── Call header — cyan left border + glassy bg ── */
.call-header {
    font-size: 17px;
    font-weight: 700;
    padding: 11px 18px;
    background: linear-gradient(90deg, #0f1117, #161b2e);
    border-left: 3px solid #00d4ff;
    border-radius: 0 10px 10px 0;
    margin: 10px 0 14px;
    color: #ffffff;
    box-shadow: inset 0 0 30px #00d4ff08;
}
.badge-ended {
    font-size: 11px;
    font-weight: 600;
    background: #1e2235;
    color: #94a3b8;
    padding: 2px 9px;
    border-radius: 10px;
    vertical-align: middle;
    margin-left: 8px;
    border: 1px solid #2a3050;
}

/* ── Demo call card — purple accent ── */
.demo-call-card {
    background: linear-gradient(90deg, #0f1117, #130d1f);
    border: 1px solid #2a1a4a;
    border-left: 3px solid #7c3aed;
    border-radius: 0 10px 10px 0;
    padding: 10px 16px;
    margin: 18px 0 8px;
    font-size: 15px;
    font-weight: 700;
    color: #e2e8f0;
}

/* ── Proposal kind badge — cyan chip ── */
.kind-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 9px;
    border-radius: 20px;
    margin: 0 4px;
    background: #00d4ff15;
    color: #00d4ff;
    font-family: monospace;
    border: 1px solid #00d4ff40;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #0f1117;
    border: 1px solid #1e2235;
    border-radius: 10px;
    padding: 12px 16px !important;
}
[data-testid="stMetricValue"] {
    color: #00d4ff !important;
    font-weight: 700;
}
[data-testid="stMetricDelta"] svg { display: none; }

/* ── Expanders ── */
details summary {
    color: #94a3b8;
    font-size: 13px;
}
details[open] summary {
    color: #00d4ff;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #09090f; }
::-webkit-scrollbar-thumb { background: #1e2235; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #00d4ff44; }


/* ── Global font override (không đè icon font) ── */
html, body, [class*="css"], .stApp {
    font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
p, label, input, textarea, select,
h1, h2, h3, h4, h5, h6,
.stMarkdown:not([data-testid*="Icon"]) {
    font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
.stButton > button {
    font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ── Bảo vệ icon Streamlit (Material Symbols / Icons) ── */
[data-testid*="Icon"],
[data-testid="stIconMaterial"],
.material-symbols-rounded,
.material-symbols-outlined,
.material-icons,
[class*="material-symbols"],
[class*="material-icons"],
[data-testid="stSidebarCollapseButton"] span,
[data-testid="stSidebarCollapseButton"] div,
[data-testid="stSidebarCollapseButton"] button {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
}
/* Keep monospace where appropriate */
code, pre, .stCode, .kind-badge,
section[data-testid="stSidebar"] .stCaption p {
    font-family: 'Space Mono', 'Courier New', monospace !important;
}

/* ── Hero Banner (compact & elevated) ── */
.stMainBlockContainer {
    padding-top: 1.5rem !important;
}
.sc-banner {
    position: relative;
    overflow: hidden;
    padding: 16px 24px 14px;
    margin: -16px -16px 12px;
    background: #09090f;
    border-bottom: 1px solid #1e2235;
}
/* subtle dot-grid background — matches brand image */
.sc-banner::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
        radial-gradient(circle, #00d4ff14 1px, transparent 1px),
        radial-gradient(circle, #7c3aed08 1px, transparent 1px);
    background-size: 28px 28px, 56px 56px;
    background-position: 0 0, 14px 14px;
    pointer-events: none;
}
/* cyan glow blob top-right — mirrors the geometric shape in brand */
.sc-banner::after {
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, #00d4ff1e 0%, #7c3aed0e 50%, transparent 70%);
    border-radius: 50%;
    pointer-events: none;
}
.sc-banner-inner { position: relative; z-index: 1; }
.sc-terminal-line {
    font-family: 'Space Mono', 'Courier New', monospace !important;
    font-size: 12px;
    color: #00d4ff;
    letter-spacing: 1.5px;
    margin-bottom: 4px;
    opacity: 0.9;
}
.sc-banner-title {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: clamp(26px, 3.8vw, 38px);
    font-weight: 800;
    letter-spacing: -1px;
    line-height: 1.1;
    margin-bottom: 4px;
    color: #ffffff;
}
.sc-banner-title .accent {
    background: linear-gradient(120deg, #00d4ff 0%, #7c3aed 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.sc-banner-sub {
    font-size: 13px;
    color: #94a3b8;
    letter-spacing: 0.2px;
    margin-top: 2px;
}
.sc-banner-pill {
    display: inline-block;
    margin-top: 6px;
    padding: 2px 10px;
    border: 1px solid #00d4ff40;
    border-radius: 20px;
    font-size: 10px;
    font-weight: 600;
    color: #00d4ff;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    background: #00d4ff0a;
}

/* ── Footer cố định ở chân trang (Fixed Bottom) ── */
.sc-footer {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100vw;
    padding: 10px 28px;
    border-top: 1px solid #1e2235;
    background: rgba(9, 9, 15, 0.95);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 24px;
    box-sizing: border-box;
}
.sc-footer-logo {
    font-family: 'Space Mono', monospace !important;
    font-size: 13px;
    color: #00d4ff;
    letter-spacing: 1.5px;
    margin: 0;
}
.sc-footer-credits {
    font-size: 12px;
    color: #64748b;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}
.sc-footer-credits strong {
    color: #e2e8f0;
    font-weight: 600;
}
.sc-footer-sep {
    color: #2a3050;
    font-size: 16px;
    line-height: 1;
}
.sc-footer-label {
    color: #94a3b8;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 600;
}

/* Khoảng đệm đáy để nội dung cuộn không bị footer che */
.stMainBlockContainer {
    padding-bottom: 75px !important;
}
</style>
""", unsafe_allow_html=True)


def money(v):
    return f"{v:,}đ".replace(",", ".") if isinstance(v, int) else ("—" if v is None else str(v))


def get_engine():
    cfg = st.session_state.get("cfg")
    want = (st.session_state.get("ns_name", "demo"), cfg["config"], cfg["router"], cfg["generator"])
    if st.session_state.get("engine_key") != want:
        if st.session_state.get("engine"):
            st.session_state["engine"].end_call()
        st.session_state["engine"] = E.Engine(want[0], want[1], want[2], want[3])
        st.session_state["engine_key"] = want
    return st.session_state["engine"]


# ---------- thanh bên ----------
with st.sidebar:
    st.markdown("### 🛠 Cấu hình")
    st.session_state["ns_name"] = st.text_input("Tên khách demo (namespace)", st.session_state.get("ns_name", "demo"))
    cfg = {
        "config": st.radio("Chế độ", ["full", "baseline_no_memory"], horizontal=True,
                           help="baseline_no_memory: không đọc bộ nhớ phiên trước (vẫn ghi)"),
        "router": st.selectbox("Router", ["rules", "jev", "qwen", "llm"], help="jev/qwen/llm cần key hoặc server"),
        "generator": st.selectbox("Generator", ["offline", "qwen", "deepseek"],
                                  help="offline = câu mẫu, không cần mạng; qwen cần vLLM; deepseek cần key"),
    }
    st.session_state["cfg"] = cfg
    eng = get_engine()
    st.caption(f"Namespace `{eng.ns}`")
    st.caption(f"Database `{os.environ.get('DATABASE_URL')}`")
    if st.button("🗑 Xoá bộ nhớ khách", type="secondary"):
        eng.reset()
        st.success("Đã xoá bộ nhớ + reset mock")

# ---------- Banner ----------
st.markdown("""
<div class="sc-banner">
  <div class="sc-banner-inner">
    <div class="sc-terminal-line">&gt;&nbsp;$sudo&nbsp;code_</div>
    <div class="sc-banner-title">SUDO&nbsp;<span class="accent">CODE</span></div>
    <div class="sc-banner-sub">Telesale AI Agent &nbsp;·&nbsp; Demo &amp; Evaluation Platform</div>
    <div class="sc-banner-pill">demo</div>
  </div>
</div>
""", unsafe_allow_html=True)

tab_call, tab_demo, tab_mem, tab_metrics, tab_improve = st.tabs(
    ["Cuộc gọi", "Demo C.6", "Bộ nhớ", "Chỉ số", "Cải tiến"])


def show_brief(brief):
    if not brief:
        return
    if not brief.get("is_returning"):
        st.info("Khách mới — chưa có lịch sử.")
        return
    st.subheader("Call Brief · khách gọi lại")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Khách:** {brief.get('honorific') or ''} {brief.get('customer_name') or ''} · {brief.get('customer_phone') or ''}")
        st.markdown(f"**Số phiên trước:** {brief.get('n_previous_sessions')}")
        last = brief.get("last_session") or {}
        st.markdown(f"**Phiên gần nhất:** {last.get('date')} ({last.get('channel')}) — {last.get('outcome')}")
        st.caption(last.get("summary") or "")
        if brief.get("suggested_opening"):
            st.markdown(f"**Mở đầu gợi ý:** _{brief['suggested_opening']}_")
        if brief.get("suggested_next_action"):
            st.markdown(f"**Việc nên làm:** {brief['suggested_next_action']}")
    with c2:
        st.markdown("**Không hỏi lại:** " + (", ".join(f"`{x}`" for x in brief.get("must_not_ask") or []) or "—"))
        facts = brief.get("profile_facts") or {}
        if facts:
            st.table([{"slot": k, "giá trị": json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}
                      for k, v in facts.items()])
        for p in brief.get("products_advised") or []:
            st.markdown(f"- {p['sku']}: báo {money(p.get('price_quoted_vnd'))} ngày {p.get('quoted_on')}, "
                        f"giờ {money(p.get('current_price_vnd'))}, KM {p.get('promo_code') or '—'}"
                        + ("" if p.get("promo_still_active") in (None, True) else " (**KM đã hết**)"))
        for o in brief.get("orders") or []:
            st.markdown(f"- Đơn {o.get('order_id')}: {o.get('status')} · giao dự kiến {o.get('estimated_delivery')}")
        for w in brief.get("stale_warnings") or []:
            st.warning(w)
    st.caption(f"Call Brief dựng trong {brief.get('latency_ms')} ms")


def show_turn(row):
    with st.chat_message("user"):
        st.write(row.get("customer_text"))
    with st.chat_message("assistant"):
        st.write(row.get("agent_text"))
        # F mức M2: cảnh báo khi agent SẮP cam kết sai — bản nháp bị guardrail chặn (số tiền lạ, đọc giá khách nêu,
        # giá cũ, lộ PII…) và câu cuối còn chứa cụm cam kết
        g = row.get("guardrail") or {}
        if g.get("rejected"):
            why = "; ".join((g.get("problems") or []) + (g.get("coverage") or [])) or g.get("action") or ""
            st.warning(f"Guardrail đã chặn {len(g['rejected'])} bản nháp ({why}). Bản nháp đầu: “{g['rejected'][0][:160]}”")
        if PROMISE_RX.search(row.get("agent_text") or ""):
            st.error("Câu trả lời có cụm cam kết (cam kết / đảm bảo / chắc chắn…). Nhân viên kiểm lại trước khi nói với khách.")
        with st.expander("chi tiết lượt", expanded=False):
            st.markdown(f"**goal:** {', '.join(row.get('goals') or [])} · **intent:** {(row.get('router') or {}).get('intent')}")
            br = (row.get("planner") or {}).get("branches") or []
            if br:
                st.markdown("**planner:** " + "; ".join(f"{b['branch']} ({b.get('reason')})" for b in br))
            tools = row.get("tool_calls") or []
            if tools:
                st.markdown("**tool:** " + ", ".join(t["name"] for t in tools))
            g = row.get("guardrail") or {}
            if g.get("problems") or g.get("action"):
                st.markdown(f"**guardrail:** {g.get('action')} {g.get('problems') or ''}")
            if row.get("claims"):
                st.json(row["claims"], expanded=False)
            if row.get("memory_writes"):
                st.markdown("**ghi bộ nhớ:** " + ", ".join(f"{w.get('key')}={w.get('value')} ({w.get('op')})"
                                                          for w in row["memory_writes"]))


# ---------- Cuộc gọi ----------
with tab_call:
    eng = get_engine()
    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
    phone = c1.text_input("SĐT khách", E.DEMO_PHONE)
    channel = c2.selectbox("Kênh", E.CHANNELS)
    day = c3.date_input("Ngày gọi", value=None, help="để trống = 2026-10-15 (reference_date của đề)")
    ident = c4.text_input("Zalo/FB id (kênh chat)", "")
    b1, b2 = st.columns(2)
    if b1.button("▶  Bắt đầu cuộc gọi mới", type="primary"):
        eng.start_call(phone, channel, day.isoformat() if day else None, ident or None)
    if b2.button("⏹  Kết thúc cuộc gọi") and eng.sess:
        eng.end_call()
        st.success("đã lưu phiên vào bộ nhớ")
    if eng.calls:
        cur = eng.calls[-1]
        ended_badge = "" if eng.sess else " <span class='badge-ended'>Đã kết thúc</span>"
        st.markdown(
            f"<div class='call-header'>📞 {cur['call']} &nbsp;·&nbsp; 📅 {cur['date']} &nbsp;·&nbsp; {cur['channel']}{ended_badge}</div>",
            unsafe_allow_html=True,
        )
        show_brief(cur["brief"])
        for row in cur["turns"]:
            show_turn(row)
        if eng.sess:
            msg = st.chat_input("Khách nói…")
            if msg:
                show_turn(eng.say(msg))
    else:
        st.caption("Bấm “Bắt đầu cuộc gọi mới”. Gọi lần hai với cùng SĐT để thấy Call Brief.")

# ---------- Demo C.6 ----------
with tab_demo:
    eng = get_engine()
    st.markdown("Kịch bản đề bài C.6: **cuộc 1** tư vấn, báo giá + KM, hẹn hỏi người nhà → **cuộc 2** (3 ngày sau) "
                "nhận diện khách, Call Brief, không hỏi lại, chốt đơn → **cuộc 3** (M2) hỏi vận đơn.")
    n = st.radio("Chạy tới cuộc", [1, 2, 3], index=1, horizontal=True)
    if st.button("Chạy demo từ đầu", type="primary"):
        with st.spinner("đang chạy…"):
            eng.run_demo(upto=n)
    for c in eng.calls:
        st.markdown(
            f"<div class='demo-call-card'>📞 {c['call']} &nbsp;·&nbsp; 📅 {c['date']}</div>",
            unsafe_allow_html=True,
        )
        show_brief(c["brief"])
        for row in c["turns"]:
            show_turn(row)

# ---------- Bộ nhớ ----------
with tab_mem:
    eng = get_engine()
    cid = eng.customer_id()
    if not cid:
        st.caption("Chưa có khách nào trong namespace này.")
    else:
        st.markdown(f"Khách `{cid}` · namespace `{eng.ns}`")
        ev = eng.timeline(cid)
        _fc1, _fc2 = st.columns([3, 1])
        kinds = _fc1.multiselect("Hiện loại", ["phiên", "báo giá", "fact"], default=["phiên", "báo giá", "fact"])
        only_cur = _fc2.checkbox("Ẩn superseded", value=False)
        rows = [e for e in ev if e["kind"] in kinds and not (only_cur and e["status"].startswith("superseded"))]
        st.dataframe([{"ngày": e["date"], "loại": e["kind"], "mục": e["what"],
                       "nội dung": e["detail"] if isinstance(e["detail"], str) else json.dumps(e["detail"], ensure_ascii=False),
                       "nguồn": e["source"], "trạng thái": e["status"]} for e in rows], width='stretch')

# ---------- Chỉ số ----------
with tab_metrics:
    reps = E.reports()
    if not reps:
        st.caption("Chưa có report.json dưới runs/. Chạy: `python eval/reference_eval.py --scenarios … --trace full.jsonl "
                   "--baseline base.jsonl --out report.json` (hoặc kéo kết quả Kaggle về runs/kaggle/).")
    else:
        pick = st.selectbox("report.json", reps, format_func=lambda p: os.path.relpath(p, E.ROOT))
        rep = json.load(open(pick, encoding="utf-8"))
        st.markdown(f"{rep.get('n_scenarios')} kịch bản")
        _sys = rep.get("system") or {}
        _bas = rep.get("baseline") or {}
        _sys_tsr  = (_sys.get("task_success_rate")  or {}).get("value")
        _bas_tsr  = (_bas.get("task_success_rate")  or {}).get("value")
        _sys_rec  = (_sys.get("memory_recall")      or {}).get("value")
        _bas_rec  = (_bas.get("memory_recall")      or {}).get("value")
        _sys_prec = (_sys.get("no_redundant_ask")   or {}).get("value")
        _bas_prec = (_bas.get("no_redundant_ask")   or {}).get("value")
        _m1, _m2, _m3 = st.columns(3)
        if _sys_tsr is not None:
            _d = round(_sys_tsr - _bas_tsr, 3) if _bas_tsr is not None else None
            _m1.metric("Task Success Rate",  f"{_sys_tsr:.1%}",  f"{_d:+.1%}" if _d is not None else None)
        if _sys_rec is not None:
            _d2 = round(_sys_rec - _bas_rec, 3) if _bas_rec is not None else None
            _m2.metric("Memory Recall",      f"{_sys_rec:.1%}",  f"{_d2:+.1%}" if _d2 is not None else None)
        if _sys_prec is not None:
            _d3 = round(_sys_prec - _bas_prec, 3) if _bas_prec is not None else None
            _m3.metric("No Redundant Ask",   f"{_sys_prec:.1%}", f"{_d3:+.1%}" if _d3 is not None else None)
        st.table([{"Chỉ số": t, "Baseline": b, "Hệ thống (full)": s} for t, b, s in E.metric_table(rep)])
        comp = rep.get("comparison") or {}
        if comp:
            st.markdown(" · ".join(f"**{k}**: {v}" for k, v in comp.items()))
        fails = ((rep.get("system") or {}).get("task_success_rate") or {}).get("failures") or []
        if fails:
            with st.expander(f"{len(fails)} cuộc gọi trượt TSR"):
                st.table([{"scenario": f["scenario"], "call": f["call"], "ca khó": f.get("hard_case"),
                           "lý do": "; ".join(f.get("reasons") or [])} for f in fails])

# ---------- Cải tiến ----------
with tab_improve:
    from improve import store as S
    st.markdown("Đề xuất trong `improve/pending/`. Chỉ bản trong `approved/` mới được agent nạp (khi bật ở mục E).")
    by = st.text_input("Người duyệt", st.session_state.get("reviewer", ""))
    st.session_state["reviewer"] = by
    pend = sorted(S.list_state("pending"), key=lambda p: ((p.get("context") or {}).get("id") or "~", p["id"]))
    if not pend:
        st.caption("Không có đề xuất chờ duyệt.")
    last_ctx = None
    for p in pend:
        ctx = p.get("context") or {}
        if ctx.get("id") and ctx["id"] != last_ctx:      # D52: thẻ context — mỗi mục bên dưới vẫn duyệt RIÊNG
            last_ctx = ctx["id"]
            st.subheader(f"Thẻ {ctx['id']}")
            st.markdown(f"**Khách:** {ctx.get('customer_text')}  \n**Agent:** {ctx.get('agent_text')}  \n"
                        f"**Tình huống:** {ctx.get('summary')}  \n**Cách xử lý:** {ctx.get('handling')}")
            st.caption("Mục kỹ thuật (planner_rule / router_cue / product_alias) duyệt xong vào gated/, "
                       "chỉ có hiệu lực khi qua cổng hồi quy (`python -m improve gate`).")
        with st.container(border=True):
            st.markdown(
                f"**{p['id']}** <span class='kind-badge'>{p['kind']}</span> {p.get('title', '')}",
                unsafe_allow_html=True,
            )
            ex = (p["payload"] or {}).get("examples") or {}
            if ex:
                st.markdown("Khớp: " + " / ".join(ex.get("match") or []) + "  \nKhông khớp: " + " / ".join(ex.get("no_match") or []))
            st.json(p["payload"], expanded=False)
            st.caption(f"tác giả {p.get('author')} · gap {', '.join(p.get('source_gaps') or []) or '—'}")
            reason = st.text_input("Lý do", key=f"r-{p['id']}")
            a1, a2 = st.columns(2)
            try:
                if a1.button("✅ Duyệt", key=f"a-{p['id']}", disabled=not by):
                    S.approve(p["id"], by, reason); st.rerun()
                if a2.button("❌ Loại", key=f"x-{p['id']}", disabled=not by):
                    S.reject(p["id"], by, reason); st.rerun()
            except S.ProposalError as e:
                st.error(str(e))
    gated = S.list_state("gated") if "gated" in S.STATES else []
    if gated:
        with st.expander(f"Chờ cổng hồi quy ({len(gated)})"):
            for p in gated:
                st.markdown(f"- **{p['id']}** `{p['kind']}` {p.get('title', '')} — {p['review']['by']}")
    with st.expander(f"Đã duyệt ({len(S.list_state('approved'))}) · hash {S.approved_hash()}"):
        for p in S.list_state("approved"):
            st.markdown(f"- **{p['id']}** `{p['kind']}` {p.get('title', '')} — {p['review']['by']}: {p['review'].get('reason')}")
    rs = S.rounds()
    if rs:
        st.table([{"vòng": m["name"], "lúc": m["at"], "người": m.get("by"), "số approved": len(m["approved_ids"]),
                   "hash": m["approved_hash"]} for m in rs])

# ---------- Footer ----------
st.markdown("""
<div class="sc-footer">
  <div class="sc-footer-logo">&gt;&nbsp;$sudo&nbsp;code_</div>
  <div class="sc-footer-credits">
    <span class="sc-footer-label">Designed & Developed </span>
    <strong>Bùi Thành Đồng</strong>
    <span class="sc-footer-sep">|</span>
    <span class="sc-footer-label">Mentor</span>
    <strong>Trần Nguyễn Duy Bảo</strong>
  </div>
</div>
""", unsafe_allow_html=True)
