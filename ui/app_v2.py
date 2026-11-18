"""Giao diện v2 (17/11) — cùng engine / backend / dữ liệu với ui/app.py, chỉ đổi bố cục cho nhân viên telesale.

    UI_PROFILE=b2_v52n streamlit run ui/app_v2.py        # máy cá nhân
    python kaggle/ui_tunnel_v2.py                        # Kaggle: như kaggle/ui_tunnel.py nhưng mở app_v2

Vì sao là tệp mới: ui/app.py nằm trong freeze v52n-ui2 mà R0 / R1 đang dùng (cổng R1 kiểm đủ 256 tệp). Bố cục mới để riêng ở đây,
không đổi tệp nào trong freeze; sau R1 mới thay app.py (freeze mới). Không đổi hành vi agent: mọi lượt vẫn qua ui/engine.py.

Bố cục:
- Cuộc gọi   chat ở giữa, Call Brief bên phải (nhu cầu, sản phẩm đã tư vấn, việc còn chờ, cảnh báo); mỗi câu chỉ có nội dung +
             👍 / "Cần cải thiện" (mở ô ghi chú); latency / audit / tool / FAQ trong "Chi tiết lượt".
- Thanh bên  chỉ cái nhân viên cần + cảnh báo ảnh hưởng cuộc gọi; namespace / DB / hash / backend trong "Thông tin hệ thống".
- Bộ nhớ     timeline theo ngày (phiên, báo giá, hành động, fact mới); bảng fact kỹ thuật mở khi cần.
- Cải tiến   từng bước: 1 Tiếp nhận → 2 Soạn nháp → 3 Duyệt & đóng gói.
"""
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from ui import engine as E  # noqa: E402  (đặt env cho core trước khi core được import)
from improve.store import PROMISE_RX  # noqa: E402

st.set_page_config(page_title="SUDO CODE · Telesale agent", layout="wide")


def password_gate():
    """UI_PASSWORD đặt (bắt buộc khi mở UI ra ngoài, vd kaggle/ui_tunnel*.py) → phải nhập đúng mới thấy UI. Không đặt = máy cá nhân."""
    import hmac
    want = os.environ.get("UI_PASSWORD") or ""
    if not want or st.session_state.get("auth_ok"):
        return
    st.title("SUDO CODE · Telesale agent")
    pw = st.text_input("Mật khẩu", type="password")
    if pw and hmac.compare_digest(pw.encode(), want.encode()):
        st.session_state["auth_ok"] = True
        st.rerun()
    if pw:
        st.error("Sai mật khẩu.")
    st.stop()


password_gate()

SLOT_LABEL = {"room_area_m2": "Diện tích phòng (m²)", "has_children": "Có con nhỏ", "household_size": "Số người trong nhà",
              "budget_vnd": "Ngân sách", "size": "Size", "color": "Màu", "payment": "Thanh toán", "product_advised": "Sản phẩm đã tư vấn",
              "price_quoted_vnd": "Giá đã báo", "blocker": "Còn vướng", "objection": "Phản đối", "baby_age": "Tuổi bé",
              "owned_product": "Đang dùng", "competitor_price_vnd": "Giá đối thủ khách nêu", "callback_requested": "Hẹn gọi lại"}
HIDE_SLOTS = {"phone", "address"}                                  # không đọc PII lên màn hình


def money(v):
    return f"{v:,}đ".replace(",", ".") if isinstance(v, int) else ("—" if v is None else str(v))


def show_val(k, v):
    if isinstance(v, bool):
        return "có" if v else "không"
    if isinstance(v, int) and k.endswith("_vnd"):
        return money(v)
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def as_text(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("text") or x.get("summary") or x.get("value") or json.dumps(x, ensure_ascii=False)
    return str(x)


@st.cache_resource
def boot():
    return E.startup_check()


def get_engine():
    want = (st.session_state.get("ns_name", "demo"), st.session_state.get("config", "full"))
    engines = st.session_state.setdefault("engines", {})
    if want not in engines:                        # Full / Baseline: engine + namespace + session riêng, không switch settings
        engines[want] = E.Engine(want[0], want[1])
    return engines[want]


BOOT = boot()

# ---------- thanh bên: chỉ cái nhân viên cần + cảnh báo ảnh hưởng cuộc gọi ----------
with st.sidebar:
    st.markdown("### SUDO CODE · Telesale")
    if BOOT["ok"]:
        st.success("Sẵn sàng · " + (E.PROFILE_INFO.get("label") or "").split(",")[0])
    else:
        st.error("Không mở được cuộc gọi B2 — xem cảnh báo")
        for m in BOOT["mismatch"]:
            st.caption(f"⚠ {m}")
    missing = [k for k, v in (BOOT.get("keys_present") or {}).items() if not v]
    if missing:
        st.warning("Thiếu khóa API: " + ", ".join(missing))
    if "khác cấu hình đo" in (BOOT.get("label") or ""):
        st.warning("Đang chạy KHÁC cấu hình đo (không có Qwen compose) — chỉ để xem.")
    st.session_state["reviewer"] = st.text_input("Tên nhân viên", st.session_state.get("reviewer", ""),
                                                 help="bắt buộc để đánh giá câu trả lời và duyệt FAQ")
    st.session_state["ns_name"] = st.text_input("Khách demo", st.session_state.get("ns_name", "demo"),
                                                help="mỗi tên = một bộ nhớ khách riêng")
    st.session_state["config"] = st.radio("Chế độ", ["full", "baseline_no_memory"], horizontal=True,
                                          format_func=lambda x: "Có bộ nhớ" if x == "full" else "Không bộ nhớ (baseline)")
    eng = get_engine()
    pkg = E.active_package()
    st.caption("Gói FAQ: " + (f"đang bật ({str(pkg.get('approved_hash'))[:12]})" if pkg.get("package") else "tắt"))
    with st.expander("Thông tin hệ thống"):
        st.caption(BOOT["label"])
        st.caption(f"ARCH={BOOT['arch']} · PLANNER_VARIANT={BOOT['planner_variant']}")
        if E.PROFILE_INFO.get("snapshot"):
            st.caption(f"snapshot `{E.PROFILE_INFO['snapshot']}`")
        if E.PROFILE_INFO.get("code"):
            _c = E.PROFILE_INFO["code"]
            st.caption(f"Code: freeze `{_c['freeze']}` · " + {"ok": f"khớp {_c['checked']} tệp", "mismatch": f"LỆCH {len(_c['bad'])} tệp",
                                                              "absent": "chưa kiểm (không có tệp freeze)", "none": "không khai báo"}[_c["status"]])
        if BOOT.get("keys_present"):
            st.caption("Key API: " + ", ".join(f"{k} {'có' if v else 'THIẾU'}" for k, v in BOOT["keys_present"].items()))
        st.caption(f"namespace `{eng.ns}` · DB `{os.environ.get('DATABASE_URL')}`")
        st.caption(f"Gói FAQ: `{os.path.relpath(pkg['package'], E.ROOT) if pkg.get('package') else '—'}` · hash {pkg.get('approved_hash')} "
                   "— áp dụng cho cuộc gọi mở sau")
        if st.button("Xoá bộ nhớ khách này", disabled=eng.sess is not None):
            eng.reset()
            st.success("đã xoá bộ nhớ + reset mock")
    if st.button("Chuẩn bị dữ liệu UI để tải về", help="feedback, trace UI, bộ nhớ UI, kho duyệt FAQ — tải về trước khi phiên Kaggle tắt"):
        st.session_state["ui_zip"] = E.export_ui_data()
    if st.session_state.get("ui_zip"):
        st.download_button("Tải ui_data.zip", st.session_state["ui_zip"], file_name="ui_data.zip", mime="application/zip")

tab_call, tab_demo, tab_mem, tab_metrics, tab_improve = st.tabs(["Cuộc gọi", "Demo C.6", "Bộ nhớ", "Chỉ số", "Cải tiến"])


# ---------- Call Brief (cột phải) ----------
def show_brief(brief, compact=False):
    if not brief:
        return
    if not brief.get("is_returning"):
        st.info("Khách mới — chưa có lịch sử.")
        return
    st.subheader("Call Brief · khách gọi lại")
    name = f"{brief.get('honorific') or ''} {brief.get('customer_name') or ''}".strip() or "—"
    last = brief.get("last_session") or {}
    st.markdown(f"**{name}** · đã gọi {brief.get('n_previous_sessions')} lần  \n"
                f"Lần gần nhất {last.get('date') or '—'} ({last.get('channel') or '—'}) — {last.get('outcome') or '—'}")
    if last.get("summary"):
        st.caption(last["summary"])
    for w in brief.get("stale_warnings") or []:
        st.warning(as_text(w))
    facts = {k: v for k, v in (brief.get("profile_facts") or {}).items() if k not in HIDE_SLOTS}
    if facts:
        st.markdown("**Nhu cầu đã biết**")
        st.markdown("\n".join(f"- {SLOT_LABEL.get(k, k)}: {show_val(k, v)}" for k, v in facts.items()))
    prods = brief.get("products_advised") or []
    if prods:
        st.markdown("**Đã tư vấn**")
        for p in prods:
            gone = p.get("promo_still_active") is False
            st.markdown(f"- {p['sku']}: báo {money(p.get('price_quoted_vnd'))} ({p.get('quoted_on')}) · giờ {money(p.get('current_price_vnd'))}"
                        + (f" · KM {p['promo_code']}" if p.get("promo_code") else "") + (" · **KM đã hết**" if gone else ""))
    for o in brief.get("orders") or []:
        st.markdown(f"- Đơn {o.get('order_id')}: {o.get('status')} · giao dự kiến {o.get('estimated_delivery')}")
    pending = [as_text(x) for x in (brief.get("open_blockers") or []) + (brief.get("open_questions") or [])]
    if pending or brief.get("suggested_next_action"):
        st.markdown("**Việc còn chờ**")
        st.markdown("\n".join([f"- {x}" for x in pending] + ([f"- ➜ {brief['suggested_next_action']}"]
                                                              if brief.get("suggested_next_action") else [])))
    if not compact:
        if brief.get("suggested_opening"):
            st.caption(f"Mở đầu gợi ý: {brief['suggested_opening']}")
        with st.expander("Không hỏi lại / thông số brief"):
            st.markdown(", ".join(SLOT_LABEL.get(x, x) for x in brief.get("must_not_ask") or []) or "—")
            st.caption(f"Call Brief dựng trong {brief.get('latency_ms')} ms")


# ---------- mỗi tin nhắn: nội dung + đánh giá nhỏ; chi tiết gập ----------
def feedback_row(eng, row):
    ui = row.get("ui") or {}
    mid = ui.get("msg_id")
    if not mid:
        return
    done = st.session_state.setdefault("fb_done", {})
    if mid in done:
        st.caption("đã đánh giá: " + ("👍" if done[mid] == 1 else "cần cải thiện"))
        return
    by = st.session_state.get("reviewer", "")
    opened = st.session_state.setdefault("fb_open", {})
    b1, b2, _ = st.columns([1, 3, 8])
    if b1.button("👍", key=f"up-{mid}", disabled=not by, help="nhập tên nhân viên ở thanh bên" if not by else "câu này tốt"):
        eng.feedback(row, 1, "", by)
        done[mid] = 1
        st.rerun()
    if b2.button("Cần cải thiện", key=f"dn-{mid}", disabled=not by, help="nhập tên nhân viên ở thanh bên" if not by else None):
        opened[mid] = True
    if opened.get(mid):
        note = st.text_input("Chưa ổn ở đâu? (tuỳ chọn)", key=f"note-{mid}", placeholder="vd: chưa nói khuyến mãi, hỏi lại điều đã biết…")
        if st.button("Gửi", key=f"send-{mid}"):
            eng.feedback(row, -1, note, by)
            done[mid] = -1
            opened.pop(mid, None)
            st.rerun()


def show_turn(eng, row, feedback=True):
    with st.chat_message("user"):
        st.write(row.get("customer_text"))
    with st.chat_message("assistant"):
        ui = row.get("ui") or {}
        text = ui.get("emitted_text") if ui.get("emitted_text") is not None else row.get("agent_text")
        st.write(text)
        if ui and ui.get("emitted_text") != row.get("agent_text"):
            st.error("Câu phát qua on_emit khác agent_text của trace — kiểm lại.")
        if PROMISE_RX.search(text or ""):
            st.warning("Có cụm cam kết (cam kết / đảm bảo / chắc chắn…) — kiểm lại trước khi nói với khách.")
        if feedback:
            feedback_row(eng, row)
        with st.expander("Chi tiết lượt"):
            lat = row.get("latency") or {}
            imp = row.get("improve") or {}
            st.caption(f"phát sau {lat.get('total_ms')} ms (TTFT = Total, không stream) · audit {row.get('audit_status')}"
                       + (f" · FAQ dùng {imp.get('used')}" if imp.get("used") else ""))
            g = row.get("guardrail") or {}
            if g.get("rejected"):
                why = "; ".join((g.get("problems") or []) + (g.get("coverage") or [])) or g.get("action") or ""
                st.caption(f"Guardrail đã chặn {len(g['rejected'])} bản nháp ({why}).")
            st.markdown(f"**goal:** {', '.join(row.get('goals') or [])} · **intent:** {(row.get('router') or {}).get('intent')}")
            lp = (row.get("planner") or {}).get("loop") or {}
            if lp.get("steps"):
                st.markdown("**B2 steps:** " + " → ".join(f"{s.get('action')}{':' + s['request_ref'] if s.get('request_ref') else ''}"
                                                          f"({s.get('status')})" for s in lp["steps"]))
            tools = row.get("tool_calls") or []
            if tools:
                st.markdown("**tool:** " + ", ".join(t["name"] for t in tools))
            if imp:
                st.json(imp, expanded=False)
            if row.get("memory_writes"):
                st.markdown("**ghi bộ nhớ:** " + ", ".join(f"{w.get('key')} ({w.get('op')})" for w in row["memory_writes"]))


# ---------- Cuộc gọi: chat giữa, brief phải ----------
with tab_call:
    eng = get_engine()
    can_call = BOOT["ok"] or E.PROFILE_INFO["profile"] not in E.B2_PROFILES
    with st.expander("Thiết lập cuộc gọi", expanded=not eng.calls):
        c1, c2, c3, c4 = st.columns(4)
        phone = c1.text_input("SĐT khách (mô phỏng)", E.DEMO_PHONE)
        channel = c2.selectbox("Kênh", E.CHANNELS)
        day = c3.date_input("Ngày gọi", value=None, help="để trống = 2026-10-15 (reference_date của đề)")
        ident = c4.text_input("Zalo/FB id (kênh chat)", "")
    b1, b2, _ = st.columns([2, 2, 6])
    if b1.button("Bắt đầu cuộc gọi mới", type="primary", disabled=not can_call):
        eng.start_call(phone, channel, day.isoformat() if day else None, ident or None)
    if b2.button("Kết thúc cuộc gọi", disabled=eng.sess is None):
        with st.spinner("đang lưu phiên (chờ audit nền xong)…"):
            eng.end_call()
        st.success("đã lưu phiên vào bộ nhớ")
    if eng.calls:
        cur = eng.calls[-1]
        left, right = st.columns([3, 2], gap="large")
        with left:
            st.markdown(f"**{cur['call']}** · {cur['date']} · {cur['channel']}" + ("" if eng.sess else " · đã kết thúc"))
            for row in cur["turns"]:
                show_turn(eng, row)
            if eng.sess:
                msg = st.chat_input("Khách nói…")
                if msg:
                    eid = hashlib.sha1(f"{cur['session_id']}|{len(cur['turns'])}|{msg}".encode()).hexdigest()[:16]
                    with st.spinner("agent đang trả lời…"):
                        eng.say(msg, event_id=eid)
                    st.rerun()
        with right, st.container(border=True):
            show_brief(cur["brief"])
    else:
        st.caption("Bấm “Bắt đầu cuộc gọi mới”. Gọi lần hai với cùng SĐT để thấy Call Brief.")

# ---------- Demo C.6 ----------
with tab_demo:
    eng = get_engine()
    st.markdown("Kịch bản đề bài C.6: **cuộc 1** tư vấn, báo giá + KM, hẹn hỏi người nhà → **cuộc 2** (3 ngày sau) "
                "nhận diện khách, Call Brief, không hỏi lại, chốt đơn → **cuộc 3** (M2) hỏi vận đơn.")
    n = st.radio("Chạy tới cuộc", [1, 2, 3], index=1, horizontal=True)
    if st.button("Chạy demo từ đầu", type="primary", disabled=eng.sess is not None):
        with st.spinner("đang chạy…"):
            eng.run_demo(upto=n)
    for c in eng.calls:
        st.markdown(f"---\n### {c['call']} · {c['date']}")
        left, right = st.columns([3, 2], gap="large")
        with left:
            for row in c["turns"]:
                show_turn(eng, row, feedback=False)
        with right, st.container(border=True):
            show_brief(c["brief"], compact=True)

# ---------- Bộ nhớ: timeline theo ngày; bảng kỹ thuật khi cần ----------
with tab_mem:
    eng = get_engine()
    cid = eng.customer_id()
    if not cid:
        st.caption("Chưa có khách nào trong bộ nhớ này.")
    else:
        ev = eng.timeline(cid)
        days = {}
        for e in ev:
            days.setdefault(e["date"] or "—", []).append(e)
        for d, items in days.items():
            with st.container(border=True):
                st.markdown(f"**{d}**")
                for e in items:
                    det = e["detail"]
                    if e["kind"] == "phiên":
                        st.markdown(f"📞 {e['what']}")
                        if det:
                            st.caption(det)
                    elif e["kind"] == "báo giá":
                        st.markdown(f"💬 Báo giá {e['what']}: {money((det or {}).get('giá'))}"
                                    + (f" · KM {det.get('KM')} (hết {det.get('KM hết hạn')})" if (det or {}).get("KM") else ""))
                    elif e["kind"] == "hành động":
                        st.markdown(f"✅ {e['what']} " + " · ".join(f"{k} {v}" for k, v in (det or {}).items())
                                    + (" — **lỗi**" if e["status"] == "lỗi" else ""))
                    elif e["what"] not in HIDE_SLOTS:
                        old = e["status"].startswith("superseded")
                        txt = f"{SLOT_LABEL.get(e['what'], e['what'])}: {show_val(e['what'], det)}"
                        st.markdown(f"📝 ~~{txt}~~ (đã thay)" if old else f"📝 {txt}")
        with st.expander("Bảng fact kỹ thuật (có nguồn, trạng thái, hết hạn)"):
            kinds = st.multiselect("Hiện", ["phiên", "báo giá", "fact", "hành động"], default=["fact"])
            only_cur = st.checkbox("Ẩn fact đã bị thay thế", value=False)
            rows = [e for e in ev if e["kind"] in kinds and not (only_cur and e["status"].startswith("superseded"))]
            st.dataframe([{"ngày": e["date"], "loại": e["kind"], "mục": e["what"],
                           "nội dung": e["detail"] if isinstance(e["detail"], str) else json.dumps(e["detail"], ensure_ascii=False),
                           "nguồn": e["source"], "trạng thái": e["status"]} for e in rows], width="stretch")

# ---------- Chỉ số ----------
with tab_metrics:
    reps = E.reports()
    if not reps:
        st.caption("Chưa có report.json dưới runs/.")
    else:
        pick = st.selectbox("Report", range(len(reps)), format_func=lambda i: reps[i]["label"])
        meta = reps[pick]
        st.markdown(f"**Phiên bản:** {meta['version']} · **Bộ dữ liệu:** {meta['dataset']} · **Backend:** {meta['backend']} · "
                    f"**Ngày đo:** {meta['measured']}")
        if meta["version"] == "?":
            st.warning("Report chưa gắn nhãn phiên bản — không dùng làm số hiện hành.")
        rep = json.load(open(meta["path"], encoding="utf-8"))
        st.markdown(f"{rep.get('n_scenarios')} kịch bản")
        st.table([{"Chỉ số": t, "Baseline": b, "Hệ thống (full)": s} for t, b, s in E.metric_table(rep)])
        fails = ((rep.get("system") or {}).get("task_success_rate") or {}).get("failures") or []
        if fails:
            with st.expander(f"{len(fails)} cuộc gọi trượt TSR"):
                st.table([{"scenario": f["scenario"], "call": f["call"], "ca khó": f.get("hard_case"),
                           "lý do": "; ".join(f.get("reasons") or [])} for f in fails])

# ---------- Cải tiến: từng bước ----------
STEPS = ["1 · Tiếp nhận", "2 · Soạn nháp", "3 · Duyệt & đóng gói"]
with tab_improve:
    from improve import store as S
    root = E.C5_ROOT
    by = st.session_state.get("reviewer", "")
    gaps = {}
    gp = S.paths(root)["gaps"]
    if os.path.exists(gp):
        for l in open(gp, encoding="utf-8"):
            if l.strip():
                g = json.loads(l)
                gaps[g["id"]] = g
    pend = [p for p in S.list_state("pending", root) if p["kind"] == "faq"]
    appr = [p for p in S.list_state("approved", root) if p["kind"] == "faq"]
    n_fb = sum(1 for l in open(E.FEEDBACK, encoding="utf-8") if l.strip()) if os.path.exists(E.FEEDBACK) else 0
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Feedback nhân viên", n_fb)
    m2.metric("Gap", len(gaps))
    m3.metric("Chờ duyệt", len(pend))
    m4.metric("Đã duyệt", len(appr))
    step = st.radio("Bước", STEPS, horizontal=True, label_visibility="collapsed", key="c5_step")

    if step == STEPS[0]:
        st.caption("Gap đến từ **đánh giá của nhân viên** (chỉ “Cần cải thiện” thành gap; 👍 lưu làm tín hiệu tốt) và, tùy chọn, "
                   "**điểm chấm tự động** của một lần đo dev.")
        with st.expander("Thêm điểm chấm tự động (trace + report dev)"):
            ev_trace = st.text_input("Trace dev (jsonl)", "", placeholder="runs/.../full.jsonl")
            ev_report = st.text_input("report.json tương ứng", "", placeholder="runs/.../report.json")
        if st.button("Gom gap", type="primary"):
            r = subprocess.run(E.gap_cmd(root, ev_trace or None, ev_report or None), capture_output=True, text=True, timeout=600)
            (st.success if r.returncode == 0 else st.error)(r.stdout or r.stderr)
            if r.returncode == 0 and os.path.exists(gp):
                gaps = {g["id"]: g for g in (json.loads(l) for l in open(gp, encoding="utf-8") if l.strip())}
        if gaps:
            st.caption(" · ".join(f"{k}: {v}" for k, v in E.gap_counts(gaps.values()).items()))
            st.dataframe([{"nguồn": g.get("feedback_source"), "loại": g.get("type"), "khách": g.get("customer_text"),
                           "agent": g.get("agent_text"), "ghi chú": (g.get("detail") or {}).get("note") if isinstance(g.get("detail"), dict) else None}
                          for g in list(gaps.values())[-30:]], width="stretch")

    elif step == STEPS[1]:
        st.caption("DeepSeek chỉ chọn câu chính sách theo ID; câu trả lời là câu NGUYÊN VĂN của tài liệu nguồn (code kiểm lại). "
                   "Không có nguồn phù hợp → gap giữ chưa trả lời, không bịa. Gap đã xử lý thì bỏ qua.")
        dc1, dc2 = st.columns([3, 1])
        dtypes = dc1.multiselect("Loại gap", ["staff_dislike", "no_info", "task_fail"], default=["staff_dislike", "no_info", "task_fail"])
        dlimit = dc2.number_input("Tối đa", 1, 50, 20)
        if st.button("Soạn nháp FAQ", type="primary", disabled=not (gaps and dtypes)):
            with st.spinner("DeepSeek đang soạn nháp…"):
                r = subprocess.run(E.draft_cmd(root, dtypes, dlimit), capture_output=True, text=True, timeout=1200)
            (st.success if r.returncode == 0 else st.error)(r.stdout or r.stderr[-2000:])
            dr = os.path.join(root, "draft_result.json")
            if r.returncode == 0 and os.path.exists(dr):
                res = json.load(open(dr, encoding="utf-8"))
                for k in ("unanswered", "invalid"):
                    if res.get(k):
                        with st.expander(f"{k} ({len(res[k])}) — gap giữ chưa trả lời"):
                            st.json(res[k])

    else:
        try:
            from harness import rag
            chunk_text = {c["chunk_id"]: c for c in rag.CHUNKS}
        except Exception:  # noqa: BLE001
            chunk_text = {}
        if not by:
            st.info("Nhập tên nhân viên ở thanh bên để duyệt.")
        st.markdown(f"**Chờ duyệt ({len(pend)})**")
        for p in pend:
            pl = p["payload"]
            with st.container(border=True):
                st.markdown(f"**{pl.get('topic')}**  \nKhách hỏi: {pl.get('question')}  \nTrả lời: {pl.get('answer')}")
                src = pl.get("source") or {}
                ch = chunk_text.get(src.get("chunk_id")) or {}
                t = pl.get("test") or {}
                g = gaps.get((pl.get("gap") or {}).get("id")) or {}
                with st.expander(f"Nguồn {src.get('doc')} · test · gap"):
                    st.caption(f"{src.get('chunk_id')} · {ch.get('title', '')}")
                    st.write(ch.get("text") or "(không tìm thấy chunk — loại)")
                    st.markdown(f"**Test hồi quy:** khách nói “{t.get('customer_text')}” → câu trả lời phải có "
                                + " / ".join(f"“{m}”" for m in t.get("must_say_any") or []))
                    if g:
                        st.caption(f"Gap {g['id']} ({g.get('feedback_source')}:{g['type']}) · khách: {g.get('customer_text')} · "
                                   f"agent: {g.get('agent_text')}")
                reason = st.text_input("Lý do", key=f"r-{p['id']}")
                a1, a2, _ = st.columns([2, 3, 5])
                try:
                    if a1.button("Duyệt", key=f"a-{p['id']}", disabled=not by, type="primary"):
                        S.approve(p["id"], by, reason, root=root)
                        st.rerun()
                    if a2.button("Loại (giữ gap chưa trả lời)", key=f"x-{p['id']}", disabled=not by):
                        S.reject(p["id"], by, reason, root=root)
                        st.rerun()
                except S.ProposalError as e:
                    st.error(str(e))
        with st.expander(f"Đã duyệt ({len(appr)}) · hash {S.approved_hash(root)}"):
            for p in appr:
                st.markdown(f"- **{p['payload'].get('topic')}** ({p['id']}) — {p['review']['by']}: {p['review'].get('reason')}")
        st.markdown("**Gói FAQ**")
        pdir = os.path.join(E.ROOT, "runs", "c5", "packages")
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Tên gói mới", "", placeholder="vd r1")
        if c2.button("Đóng gói FAQ đã duyệt", disabled=not (by and name and appr)):
            r = subprocess.run([sys.executable, E.C5_LOOP, "package", "--root", root, "--name", name, "--by", by,
                                "--out", os.path.join(pdir, name)], capture_output=True, text=True)
            (st.success if r.returncode == 0 else st.error)(r.stdout or r.stderr)
        pkgs = sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []
        d1, d2, d3 = st.columns([2, 2, 3])
        sel = d1.selectbox("Gói", pkgs) if pkgs else None
        reason = d3.text_input("Lý do kích hoạt / quay lui", "")
        if d2.button("Kích hoạt (cuộc gọi mở sau)", disabled=not (by and sel)):
            r = subprocess.run([sys.executable, E.C5_LOOP, "activate", "--pkg", os.path.join(pdir, sel), "--by", by, "--reason", reason,
                                "--state", E.C5_STATE], capture_output=True, text=True)
            (st.success if r.returncode == 0 else st.error)(r.stdout or r.stderr)
        if st.button("Quay lui gói trước", disabled=not by):
            r = subprocess.run([sys.executable, E.C5_LOOP, "rollback", "--by", by, "--reason", reason, "--state", E.C5_STATE],
                               capture_output=True, text=True)
            (st.success if r.returncode == 0 else st.error)(r.stdout or r.stderr)
        logp = os.path.join(E.C5_STATE, "activation_log.jsonl")
        if os.path.exists(logp):
            with st.expander("Nhật ký kích hoạt / quay lui"):
                st.table([json.loads(l) for l in open(logp, encoding="utf-8") if l.strip()][-8:])
