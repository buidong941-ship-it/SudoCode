"""Giao diện demo (đề bài C.6 + C.5) — Streamlit, TÁCH BIỆT với core.

    pip install -r requirements-ui.txt
    UI_PROFILE=b2_v52n streamlit run ui/app.py          # mặc định: backend B2-v52n (cấu hình chính 17/11, cần key API)
    UI_PROFILE=b2_v51a streamlit run ui/app.py          # đối chiếu / quay lui: env B2-v51-A
    UI_PROFILE=legacy_offline streamlit run ui/app.py   # chỉ xem giao diện, pipeline cũ, KHÔNG phải B2

Tab:
- Cuộc gọi   khung chat (câu hiện = câu backend phát qua on_emit); Call Brief khi khách quay lại; chi tiết lượt;
             like / dislike từng câu trả lời (feedback nhân viên — nguồn 2 của C.5)
- Demo C.6   cuộc 1 (tư vấn, báo giá + KM, hẹn hỏi người nhà) → cuộc 2 (chốt đơn) → cuộc 3 (hỏi vận đơn, M2)
- Bộ nhớ     dòng thời gian của khách: phiên, báo giá, fact (kể cả bị thay thế, có nguồn), kết quả hành động
- Chỉ số     report có nhãn phiên bản / bộ dữ liệu / backend / ngày đo (không lấy số cũ làm số hiện hành)
- Cải tiến   Knowledge Gap Loop: gap → bản nháp FAQ + nguồn + test → duyệt / loại (tên người duyệt) → đóng gói → kích hoạt → rollback
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
    """UI_PASSWORD đặt (bắt buộc khi mở UI ra ngoài, vd kaggle/ui_tunnel.py) → phải nhập đúng mới thấy UI. Không đặt = máy cá nhân."""
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


def money(v):
    return f"{v:,}đ".replace(",", ".") if isinstance(v, int) else ("—" if v is None else str(v))


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

# ---------- thanh bên ----------
with st.sidebar:
    st.header("Backend")
    (st.success if BOOT["ok"] else st.error)(BOOT["label"])
    if not BOOT["ok"]:
        for m in BOOT["mismatch"]:
            st.caption(f"⚠ {m}")
    st.caption(f"ARCH={BOOT['arch']} · PLANNER_VARIANT={BOOT['planner_variant']}"
               + (f" · snapshot `{E.PROFILE_INFO.get('snapshot')}`" if E.PROFILE_INFO.get("snapshot") else ""))
    if E.PROFILE_INFO.get("code"):
        _c = E.PROFILE_INFO["code"]
        st.caption(f"Code: freeze `{_c['freeze']}` · " + {"ok": f"khớp {_c['checked']} tệp", "mismatch": f"LỆCH {len(_c['bad'])} tệp",
                                                          "absent": "chưa kiểm (không có tệp freeze)", "none": "không khai báo"}[_c["status"]])
    if BOOT.get("keys_present"):
        st.caption("Key API: " + ", ".join(f"{k} {'có' if v else 'THIẾU'}" for k, v in BOOT["keys_present"].items()))
    pkg = E.active_package()
    st.caption(f"Gói FAQ đang kích hoạt: `{os.path.relpath(pkg['package'], E.ROOT) if pkg.get('package') else 'không (C.5 tắt)'}`"
               f" · hash {pkg.get('approved_hash')} — áp dụng cho cuộc gọi MỞ SAU")
    st.header("Phiên demo")
    st.session_state["ns_name"] = st.text_input("Tên khách demo (namespace)", st.session_state.get("ns_name", "demo"))
    st.session_state["config"] = st.radio("Chế độ", ["full", "baseline_no_memory"], horizontal=True,
                                          help="baseline_no_memory: không đọc bộ nhớ phiên trước (vẫn ghi); namespace riêng")
    st.session_state["reviewer"] = st.text_input("Tên nhân viên / người duyệt", st.session_state.get("reviewer", ""))
    eng = get_engine()
    st.caption(f"namespace `{eng.ns}` · DB `{os.environ.get('DATABASE_URL')}`")
    if st.button("Xoá bộ nhớ khách này", type="secondary", disabled=eng.sess is not None):
        eng.reset()
        st.success("đã xoá bộ nhớ + reset mock")
    if st.button("Chuẩn bị gói dữ liệu UI để tải về", help="feedback, trace UI, bộ nhớ UI, kho duyệt FAQ, trạng thái gói — "
                                                       "tải về trước khi phiên Kaggle tắt"):
        st.session_state["ui_zip"] = E.export_ui_data()
    if st.session_state.get("ui_zip"):
        st.download_button("Tải ui_data.zip", st.session_state["ui_zip"], file_name="ui_data.zip", mime="application/zip")

tab_call, tab_demo, tab_mem, tab_metrics, tab_improve = st.tabs(["Cuộc gọi", "Demo C.6", "Bộ nhớ", "Chỉ số", "Cải tiến"])


def show_brief(brief):
    if not brief:
        return
    if not brief.get("is_returning"):
        st.info("Khách mới — chưa có lịch sử.")
        return
    st.subheader("Call Brief · khách gọi lại")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Khách:** {brief.get('honorific') or ''} {brief.get('customer_name') or ''}")
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
                      for k, v in facts.items() if k not in ("phone", "address")])       # không đọc vẹt PII lên màn hình
        for p in brief.get("products_advised") or []:
            st.markdown(f"- {p['sku']}: báo {money(p.get('price_quoted_vnd'))} ngày {p.get('quoted_on')}, "
                        f"giờ {money(p.get('current_price_vnd'))}, KM {p.get('promo_code') or '—'}"
                        + ("" if p.get("promo_still_active") in (None, True) else " (**KM đã hết**)"))
        for o in brief.get("orders") or []:
            st.markdown(f"- Đơn {o.get('order_id')}: {o.get('status')} · giao dự kiến {o.get('estimated_delivery')}")
        for w in brief.get("stale_warnings") or []:
            st.warning(w)
    st.caption(f"Call Brief dựng trong {brief.get('latency_ms')} ms")


def feedback_box(eng, row):
    ui = row.get("ui") or {}
    mid = ui.get("msg_id")
    if not mid:
        return
    done = st.session_state.setdefault("fb_done", {})
    if mid in done:
        st.caption(f"đã ghi feedback: {'👍' if done[mid] == 1 else '👎'}")
        return
    note = st.text_input("Ghi chú (tuỳ chọn)", key=f"fbn-{mid}", label_visibility="collapsed", placeholder="ghi chú cho câu này…")
    b1, b2, _ = st.columns([1, 1, 6])
    by = st.session_state.get("reviewer", "")
    for col, rating, icon in ((b1, 1, "👍"), (b2, -1, "👎")):
        if col.button(icon, key=f"fb{rating}-{mid}", disabled=not by, help="nhập tên nhân viên ở thanh bên"):
            eng.feedback(row, rating, note, by)
            done[mid] = rating
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
        lat = row.get("latency") or {}
        st.caption(f"phát sau {lat.get('total_ms')} ms (TTFT = Total, không stream) · audit {row.get('audit_status')}"
                   + (f" · FAQ dùng {row['improve'].get('used')}" if (row.get("improve") or {}).get("used") else ""))
        g = row.get("guardrail") or {}
        if g.get("rejected"):
            why = "; ".join((g.get("problems") or []) + (g.get("coverage") or [])) or g.get("action") or ""
            st.warning(f"Guardrail đã chặn {len(g['rejected'])} bản nháp ({why}).")
        if PROMISE_RX.search(text or ""):
            st.error("Câu trả lời có cụm cam kết (cam kết / đảm bảo / chắc chắn…). Nhân viên kiểm lại trước khi nói với khách.")
        with st.expander("chi tiết lượt", expanded=False):
            st.markdown(f"**goal:** {', '.join(row.get('goals') or [])} · **intent:** {(row.get('router') or {}).get('intent')}")
            lp = (row.get("planner") or {}).get("loop") or {}
            if lp.get("steps"):
                st.markdown("**B2 steps:** " + " → ".join(f"{s.get('action')}{':' + s['request_ref'] if s.get('request_ref') else ''}"
                                                          f"({s.get('status')})" for s in lp["steps"]))
            tools = row.get("tool_calls") or []
            if tools:
                st.markdown("**tool:** " + ", ".join(t["name"] for t in tools))
            if row.get("improve"):
                st.json(row["improve"], expanded=False)
            if row.get("memory_writes"):
                st.markdown("**ghi bộ nhớ:** " + ", ".join(f"{w.get('key')} ({w.get('op')})" for w in row["memory_writes"]))
        if feedback:
            feedback_box(eng, row)


# ---------- Cuộc gọi ----------
with tab_call:
    eng = get_engine()
    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
    phone = c1.text_input("SĐT khách (mô phỏng)", E.DEMO_PHONE)
    channel = c2.selectbox("Kênh", E.CHANNELS)
    day = c3.date_input("Ngày gọi", value=None, help="để trống = 2026-10-15 (reference_date của đề)")
    ident = c4.text_input("Zalo/FB id (kênh chat)", "")
    b1, b2 = st.columns(2)
    if b1.button("Bắt đầu cuộc gọi mới", type="primary", disabled=not BOOT["ok"] and E.PROFILE_INFO["profile"] in E.B2_PROFILES):
        eng.start_call(phone, channel, day.isoformat() if day else None, ident or None)
    if b2.button("Kết thúc cuộc gọi", disabled=eng.sess is None):
        with st.spinner("đang lưu phiên (chờ audit nền xong)…"):
            eng.end_call()
        st.success("đã lưu phiên vào bộ nhớ")
    if eng.calls:
        cur = eng.calls[-1]
        st.markdown(f"### {cur['call']} · {cur['date']} · {cur['channel']}" + ("" if eng.sess else " (đã kết thúc)")
                    + f" · gói FAQ {cur.get('package_hash') or 'tắt'}")
        show_brief(cur["brief"])
        for row in cur["turns"]:
            show_turn(eng, row)
        if eng.sess:
            msg = st.chat_input("Khách nói…")
            if msg:
                eid = hashlib.sha1(f"{cur['session_id']}|{len(cur['turns'])}|{msg}".encode()).hexdigest()[:16]
                with st.spinner("agent đang trả lời…"):
                    eng.say(msg, event_id=eid)
                st.rerun()
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
        show_brief(c["brief"])
        for row in c["turns"]:
            show_turn(eng, row, feedback=False)

# ---------- Bộ nhớ ----------
with tab_mem:
    eng = get_engine()
    cid = eng.customer_id()
    if not cid:
        st.caption("Chưa có khách nào trong namespace này.")
    else:
        st.markdown(f"namespace `{eng.ns}`")
        ev = eng.timeline(cid)
        kinds = st.multiselect("Hiện", ["phiên", "báo giá", "fact", "hành động"], default=["phiên", "báo giá", "fact", "hành động"])
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

# ---------- Cải tiến (C.5 Knowledge Gap Loop) ----------
with tab_improve:
    from improve import store as S
    root = E.C5_ROOT
    by = st.session_state.get("reviewer", "")
    st.markdown(f"Kho duyệt C.5: `{os.path.relpath(root, E.ROOT)}`. Gap đến từ **điểm chấm tự động** (trace + report dev) và "
                "**like/dislike của nhân viên**. Bản nháp FAQ do DeepSeek chọn câu nguồn; câu trả lời là câu NGUYÊN VĂN của chunk "
                "policy được trích (code kiểm lại). Chỉ người duyệt mới đưa FAQ vào gói; model không kích hoạt gì.")
    gaps = {}
    gp = S.paths(root)["gaps"]
    if os.path.exists(gp):
        for l in open(gp, encoding="utf-8"):
            if l.strip():
                g = json.loads(l)
                gaps[g["id"]] = g
    st.caption(f"{len(gaps)} gap · " + ", ".join(f"{k}: {v}" for k, v in
                                                sorted({f"{g.get('feedback_source')}:{g['type']}": 0 for g in gaps.values()}.items())))
    pend = [p for p in S.list_state("pending", root) if p["kind"] == "faq"]
    st.subheader(f"Chờ duyệt ({len(pend)})")
    try:
        from harness import rag
        chunk_text = {c["chunk_id"]: c for c in rag.CHUNKS}
    except Exception:  # noqa: BLE001
        chunk_text = {}
    for p in pend:
        pl = p["payload"]
        with st.container(border=True):
            st.markdown(f"**{p['id']}** · {pl.get('topic')}  \n**Câu hỏi:** {pl.get('question')}  \n**Trả lời:** {pl.get('answer')}")
            src = pl.get("source") or {}
            ch = chunk_text.get(src.get("chunk_id")) or {}
            st.caption(f"Nguồn {src.get('chunk_id')} · {src.get('doc')} · {ch.get('title', '')}")
            with st.expander("Văn bản nguồn"):
                st.write(ch.get("text") or "(không tìm thấy chunk — loại)")
            t = pl.get("test") or {}
            st.markdown(f"**Test hồi quy đề xuất:** khách nói “{t.get('customer_text')}” → câu trả lời phải có "
                        + " / ".join(f"“{m}”" for m in t.get("must_say_any") or []))
            g = gaps.get((pl.get("gap") or {}).get("id")) or {}
            if g:
                st.caption(f"Gap {g['id']} ({g.get('feedback_source')}:{g['type']}) · khách: {g.get('customer_text')} · agent: {g.get('agent_text')}")
            reason = st.text_input("Lý do", key=f"r-{p['id']}")
            a1, a2 = st.columns(2)
            try:
                if a1.button("Duyệt FAQ + test", key=f"a-{p['id']}", disabled=not by):
                    S.approve(p["id"], by, reason, root=root); st.rerun()
                if a2.button("Loại (giữ gap chưa trả lời)", key=f"x-{p['id']}", disabled=not by):
                    S.reject(p["id"], by, reason, root=root); st.rerun()
            except S.ProposalError as e:
                st.error(str(e))
    appr = [p for p in S.list_state("approved", root) if p["kind"] == "faq"]
    with st.expander(f"Đã duyệt ({len(appr)}) · hash {S.approved_hash(root)}"):
        for p in appr:
            st.markdown(f"- **{p['id']}** {p['payload'].get('topic')} — {p['review']['by']}: {p['review'].get('reason')}")
    st.subheader("Gói FAQ")
    name = st.text_input("Tên gói mới (vd r1)", "")
    py = [sys.executable, os.path.join(E.ROOT, "scripts", "c5_loop.py")]
    c1, c2, c3 = st.columns(3)
    if c1.button("Đóng gói FAQ đã duyệt", disabled=not (by and name and appr)):
        out = os.path.join(E.ROOT, "runs", "c5", "packages", name)
        r = subprocess.run(py + ["package", "--root", root, "--name", name, "--by", by, "--out", out], capture_output=True, text=True)
        (st.success if r.returncode == 0 else st.error)(r.stdout or r.stderr)
    pkgs = sorted(os.listdir(os.path.join(E.ROOT, "runs", "c5", "packages"))) if os.path.isdir(os.path.join(E.ROOT, "runs", "c5", "packages")) else []
    sel = c2.selectbox("Gói", pkgs) if pkgs else None
    reason = c3.text_input("Lý do kích hoạt / quay lui", "")
    d1, d2 = st.columns(2)
    if d1.button("Kích hoạt gói (phiên mở sau)", disabled=not (by and sel)):
        r = subprocess.run(py + ["activate", "--pkg", os.path.join(E.ROOT, "runs", "c5", "packages", sel), "--by", by, "--reason", reason,
                                 "--state", E.C5_STATE], capture_output=True, text=True)
        (st.success if r.returncode == 0 else st.error)(r.stdout or r.stderr)
    if d2.button("Quay lui gói trước", disabled=not by):
        r = subprocess.run(py + ["rollback", "--by", by, "--reason", reason, "--state", E.C5_STATE], capture_output=True, text=True)
        (st.success if r.returncode == 0 else st.error)(r.stdout or r.stderr)
    logp = os.path.join(E.C5_STATE, "activation_log.jsonl")
    if os.path.exists(logp):
        st.table([json.loads(l) for l in open(logp, encoding="utf-8") if l.strip()][-8:])
