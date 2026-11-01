"""Giao diện demo (plan 01/11 mục F, đề bài C.6) — Streamlit, TÁCH BIỆT với core.

    pip install -r requirements-ui.txt
    streamlit run ui/app.py

Tab:
- Cuộc gọi     khung chat; Call Brief hiện khi khách gọi lại; chi tiết từng lượt (goal, tool, guardrail, claim)
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

st.set_page_config(page_title="SUDO CODE · Telesale agent", layout="wide")


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
    st.header("Cấu hình")
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
    st.caption(f"namespace `{eng.ns}` · DB `{os.environ.get('DATABASE_URL')}`")
    if st.button("Xoá bộ nhớ khách này", type="secondary"):
        eng.reset()
        st.success("đã xoá bộ nhớ + reset mock")

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
    if b1.button("Bắt đầu cuộc gọi mới", type="primary"):
        eng.start_call(phone, channel, day.isoformat() if day else None, ident or None)
    if b2.button("Kết thúc cuộc gọi") and eng.sess:
        eng.end_call()
        st.success("đã lưu phiên vào bộ nhớ")
    if eng.calls:
        cur = eng.calls[-1]
        st.markdown(f"### {cur['call']} · {cur['date']} · {cur['channel']}" + ("" if eng.sess else " (đã kết thúc)"))
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
        st.markdown(f"---\n### {c['call']} · {c['date']}")
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
        kinds = st.multiselect("Hiện", ["phiên", "báo giá", "fact"], default=["phiên", "báo giá", "fact"])
        only_cur = st.checkbox("Ẩn fact đã bị thay thế", value=False)
        rows = [e for e in ev if e["kind"] in kinds and not (only_cur and e["status"].startswith("superseded"))]
        st.dataframe([{"ngày": e["date"], "loại": e["kind"], "mục": e["what"],
                       "nội dung": e["detail"] if isinstance(e["detail"], str) else json.dumps(e["detail"], ensure_ascii=False),
                       "nguồn": e["source"], "trạng thái": e["status"]} for e in rows], use_container_width=True)

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
    pend = S.list_state("pending")
    if not pend:
        st.caption("Không có đề xuất chờ duyệt.")
    for p in pend:
        with st.container(border=True):
            st.markdown(f"**{p['id']}** · `{p['kind']}` · {p.get('title', '')}")
            st.json(p["payload"], expanded=False)
            st.caption(f"tác giả {p.get('author')} · gap {', '.join(p.get('source_gaps') or []) or '—'}")
            reason = st.text_input("Lý do", key=f"r-{p['id']}")
            a1, a2 = st.columns(2)
            try:
                if a1.button("Duyệt", key=f"a-{p['id']}", disabled=not by):
                    S.approve(p["id"], by, reason); st.rerun()
                if a2.button("Loại", key=f"x-{p['id']}", disabled=not by):
                    S.reject(p["id"], by, reason); st.rerun()
            except S.ProposalError as e:
                st.error(str(e))
    with st.expander(f"Đã duyệt ({len(S.list_state('approved'))}) · hash {S.approved_hash()}"):
        for p in S.list_state("approved"):
            st.markdown(f"- **{p['id']}** `{p['kind']}` {p.get('title', '')} — {p['review']['by']}: {p['review'].get('reason')}")
    rs = S.rounds()
    if rs:
        st.table([{"vòng": m["name"], "lúc": m["at"], "người": m.get("by"), "số approved": len(m["approved_ids"]),
                   "hash": m["approved_hash"]} for m in rs])
