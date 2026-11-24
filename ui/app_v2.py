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

Candidate tích hợp (UI_PROFILE=b2_integ_tt, freeze 20261117-integ-ui): thanh bên có hai cờ độc lập (tư vấn hai tầng B2-TT; dùng gói
hướng dẫn đang kích hoạt), áp dụng khi mở cuộc gọi. Tab Cải tiến = kho hướng dẫn điều phối: 1 Tiếp nhận & nhập nháp → 2 Duyệt TỪNG
hướng dẫn → 3 Đóng gói, regress, kích hoạt / quay lui → 4 Thử truy hồi. FAQ đã dừng mở rộng (chỉ xem lại trong mục gập).
18/11 (freeze 20261118-integ-ui3), bước 2: "Chỉnh sửa" lưu thành PHIÊN BẢN NHÁP MỚI (bản đã duyệt / đã đóng gói / đang kích hoạt
không bị sửa tại chỗ); "So sánh trước / sau (Jev thật)" chạy luồng agent thật hai phiên thử độc lập (không / có bản nháp) trong
tiến trình riêng, hiện cạnh nhau: hướng dẫn truy hồi + đưa vào Jev, hành động Jev chọn, tool, câu trả lời, thời gian.
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
    if E.CANDIDATE:
        st.markdown("**Candidate tích hợp** · áp dụng khi mở cuộc gọi")
        busy = eng.sess is not None
        eng.two_tier = st.checkbox("Tư vấn hai tầng (B2-TT)", value=eng.two_tier, disabled=busy, key=f"tt-{eng.ns}",
                                   help="B2_TWO_TIER: tìm / so sánh / giá thấp nhất chỉ đọc; giao dịch vẫn qua cổng của bản chính")
        eng.use_guidance = st.checkbox("Dùng gói hướng dẫn đang kích hoạt", value=eng.use_guidance, disabled=busy, key=f"gd-{eng.ns}",
                                       help="tắt = kho rỗng (R0); bật = gói đã duyệt + đóng gói + kích hoạt ở tab Cải tiến (R1)")
        ga = E.guidance_active()
        st.caption("Gói hướng dẫn: " + (f"{os.path.basename(ga['package'])} ({str(ga.get('approved_hash'))[:12]})"
                                        if ga.get("package") else "chưa kích hoạt gói nào"))
        st.caption(f"Chế độ {'cuộc gọi đang mở' if busy else 'cuộc gọi mới'}: **{eng.mode()}** — {E.MODE_LABEL[eng.mode()]}")
        st.caption("Gói FAQ: không nạp (candidate chỉ khác gói hướng dẫn)")
    else:
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
            if ui.get("mode"):
                st.markdown(f"**chế độ:** {ui['mode']} ({E.MODE_LABEL.get(ui['mode'], '')})"
                            + (f" · gói hướng dẫn {str(ui.get('guidance_hash'))[:12]}" if ui.get("guidance_hash") else ""))
            tt = lp.get("two_tier") or {}
            if tt:
                st.caption(f"B2-TT: tác vụ {tt.get('task')} · kết quả {tt.get('outcome')} · Jev {tt.get('jev_calls')} · tool {tt.get('tool_calls')}")
            gtr = lp.get("guidance") or {}
            if gtr.get("status") and gtr.get("status") != "disabled":
                st.caption(f"Hướng dẫn: {gtr['status']} · chọn {gtr.get('selected') or []} · đưa vào Jev {gtr.get('supplied_to_planner') or []}"
                           + (f" · lỗi {gtr.get('error')}" if gtr.get("error") else "")
                           + " — có trong prompt chưa chứng minh đã có tác dụng")
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
            st.markdown(f"**{cur['call']}** · {cur['date']} · {cur['channel']}" + ("" if eng.sess else " · đã kết thúc")
                        + (f" · chế độ {cur['mode']}" if cur.get("mode") else ""))
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


def faq_flow():
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


# ---------- Candidate: kho hướng dẫn điều phối (không lồng expander: luồng này có thể nằm cạnh luồng FAQ) ----------
GSTEPS = ["1 · Tiếp nhận & nhập nháp", "2 · Duyệt từng hướng dẫn", "3 · Đóng gói & kích hoạt", "4 · Thử truy hồi"]
SLOTS_ASKED = ["", "has_children", "budget_vnd", "room_area_m2", "household_size", "size", "color", "payment", "address"]


def run_cmd(args, timeout=600):
    r = subprocess.run(E.guidance_cmd(*args), capture_output=True, text=True, timeout=timeout, cwd=E.ROOT,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def bullets(title, items):
    if items:
        st.markdown(f"**{title}**\n" + "\n".join(f"- {x}" for x in items))


def guide_card(p, caps):
    pl = p["payload"]
    st.markdown(f"#### {pl.get('title')}")
    st.caption(f"{p['id']} · {pl.get('guide_id')} v{pl.get('version')} · tầng {pl.get('audience')} · {p.get('classification') or ''} · "
               f"soạn bởi {p.get('author')} lúc {p.get('created_at')}")
    if p.get("revision_of"):
        st.caption(f"Phiên bản sửa từ {p['revision_of']} — lý do sửa: {p.get('revision_note') or '—'}")
    c1, c2 = st.columns(2)
    with c1:
        bullets("Áp dụng khi", pl.get("applies_when"))
        bullets("Cách làm", pl.get("guidance"))
        bullets("Ví dụ khách nói", pl.get("examples"))
    with c2:
        bullets("Ngoại lệ", pl.get("exceptions"))
        bullets("Tránh", pl.get("avoid"))
        bullets("Phản ví dụ (không áp dụng)", pl.get("counterexamples"))
    need = set(pl.get("requires_capabilities") or [])
    one = "có" if need <= caps["one_tier"] else "KHÔNG (thiếu " + ", ".join(sorted(need - caps["one_tier"])) + ")"
    two = "có" if need <= caps["two_tier"] else "KHÔNG"
    st.caption(f"Năng lực cần: {', '.join(sorted(need)) or '—'} · có trên một tầng: {one} · có trên B2-TT: {two} "
               "(năng lực code khai báo; Jev có chọn đúng hay không phải kiểm bằng canary)")
    tests = p.get("tests") or []
    if tests:
        st.markdown("**Test đi kèm** (dữ liệu; chạy truy hồi thật, không model)")
        st.dataframe([{"test": t.get("name"), "khách nói": t.get("customer_text"), "nhân viên vừa hỏi": t.get("asked_slot"),
                       "asks": ", ".join(t.get("asks") or []), "B2-TT": bool(t.get("two_tier")), "kỳ vọng": t.get("expect")}
                      for t in tests], width="stretch")
    ev = E.guidance_evidence(p.get("source_gaps"))
    if ev:
        st.caption("Bằng chứng (hồ sơ local, không vào gói / prompt): " + "; ".join(
            f"{e['ev']} · {e.get('source')} · {e.get('scenario') or ''} {e.get('call') or ''} lượt {e.get('turns') or '—'}" for e in ev))
    elif p.get("source_gaps"):
        st.caption(f"Bằng chứng {p['source_gaps']}: không có evidence.jsonl trên máy này")


EDIT_LISTS = [("applies_when", "Áp dụng khi"), ("guidance", "Cách làm"), ("examples", "Ví dụ khách nói"), ("exceptions", "Ngoại lệ"),
              ("avoid", "Tránh"), ("counterexamples", "Phản ví dụ (không áp dụng)"), ("tags", "Tags")]


def lines(txt):
    return [x.strip() for x in (txt or "").splitlines() if x.strip()]


def edit_panel(p, by, root):
    """18/11: sửa → PHIÊN BẢN NHÁP MỚI (improve/guidance_edit.revise). Không ghi đè bản đang có; bản đã duyệt giữ nguyên tới khi bản
    mới được duyệt; gói đã đóng / đang kích hoạt không đổi."""
    from improve import guidance_edit as GE
    from improve import store as S
    pid, pl = p["id"], p["payload"]
    opened = st.session_state.setdefault("g_edit_open", {})
    lab = "Chỉnh sửa" if p.get("status") == "pending" else "Chỉnh sửa (tạo bản mới)"
    if st.button(lab, key=f"ged-{pid}", disabled=not by, help="nhập tên nhân viên ở thanh bên" if not by else None) and by:
        opened[pid] = True
    if not opened.get(pid):
        return
    with st.container(border=True):
        st.markdown(f"**Chỉnh sửa {pl.get('guide_id')} v{pl.get('version')} → lưu thành phiên bản nháp mới**")
        st.caption("Bản đang xem KHÔNG bị ghi đè. " + ("Bản chờ duyệt này sẽ chuyển sang “Đã loại” (thay bằng bản mới)." if p.get("status") == "pending"
                   else "Bản đã duyệt giữ nguyên tới khi bản mới được duyệt; gói đã đóng / đang kích hoạt không đổi — muốn dùng bản mới phải "
                        "duyệt, đóng gói lại và kích hoạt.") + " Test đi kèm giữ nguyên; chạy lại test và so sánh trước / sau rồi mới duyệt.")
        ch = {"title": st.text_input("Tiêu đề", pl.get("title") or "", key=f"ed-{pid}-title"),
              "audience": st.selectbox("Tầng", list(S.GUIDE_AUDIENCE), index=list(S.GUIDE_AUDIENCE).index(pl.get("audience"))
                                       if pl.get("audience") in S.GUIDE_AUDIENCE else 2, key=f"ed-{pid}-audience")}
        c1, c2 = st.columns(2)
        for i, (f, name) in enumerate(EDIT_LISTS):
            ch[f] = lines((c1 if i % 2 == 0 else c2).text_area(f"{name} (mỗi dòng một mục)", "\n".join(pl.get(f) or []), key=f"ed-{pid}-{f}"))
        capo = sorted(S.GUIDE_CAPABILITIES - {"request_commit"})
        ch["requires_capabilities"] = st.multiselect("Năng lực cần", capo, default=[c for c in pl.get("requires_capabilities") or [] if c in capo],
                                                     key=f"ed-{pid}-caps")
        ch["conflict_group"] = st.text_input("Nhóm xung đột", pl.get("conflict_group") or "", key=f"ed-{pid}-cg")
        note = st.text_input("Lý do sửa (bắt buộc)", key=f"ed-{pid}-note")
        preview = S.validate({"kind": "planner_guidance", "payload": {**pl, **ch}})
        if preview:
            st.warning("Bản sửa chưa hợp lệ (sẽ không lưu): " + "; ".join(preview))
        s1, s2, _ = st.columns([3, 1, 6])
        if s1.button("Lưu thành phiên bản mới", key=f"edsave-{pid}", type="primary", disabled=not (by and note.strip())) \
                and by and note.strip():
            try:
                nid = GE.revise(pid, ch, by, note, root=root)
                opened.pop(pid, None)
                st.session_state["g_flash"] = (f"Đã lưu {nid} (bản mới, chờ duyệt). Chạy lại test và so sánh trước / sau trước khi duyệt.")
                st.rerun()
            except S.ProposalError as e:
                st.error(str(e))
        if s2.button("Đóng", key=f"edclose-{pid}"):
            opened.pop(pid, None)
            st.rerun()


def _names(*groups):
    out = {}
    for g in groups:
        for p in g:
            pl = p.get("payload") or p
            out[p["id"]] = f"{pl.get('title') or p['id']} (v{pl.get('version')})"
    return out


def _tools_txt(tools):
    return "; ".join(f"{t['name']}({', '.join(f'{k}={v}' for k, v in (t.get('args') or {}).items())})"
                     + (" — GHI (môi trường thử)" if t.get("write") else "") + (" — lỗi" if t.get("error") else "")
                     for t in tools) or "—"


def show_compare(res, names):
    """Kết quả thử: mỗi câu một bảng Trước / Sau (lượt cuối = câu thử); toàn bộ lượt (gồm ngữ cảnh phát lại) trong mục gập."""
    st.caption(f"Thử lúc {res.get('at')} bởi {res.get('by') or '—'} · bản nháp {res.get('draft_prop')} v{res.get('draft_version')} "
               f"(payload {res.get('draft_payload_sha')}) · nền: {'không hướng dẫn (như R0)' if res.get('base') == 'empty' else 'các hướng dẫn đã duyệt'}"
               f" · B2-TT {'bật' if res.get('two_tier') else 'tắt'} · code {(res.get('code') or {}).get('status')} "
               f"{(res.get('code') or {}).get('freeze')}")
    if res.get("context"):
        st.caption("Ngữ cảnh phát lại ở cả hai phiên: " + " | ".join(res["context"]))
    st.caption(res.get("note") or "")

    def nm(ids):
        return ", ".join(names.get(i, i) for i in ids or []) or "—"

    for i, tr in enumerate(res.get("trials") or []):
        st.markdown(f"**Câu thử {i + 1}:** “{tr['text']}”")
        cols = {}
        for side in ("before", "after"):
            s = tr[side]
            last = (s.get("turns") or [{}])[-1] if s.get("turns") else {}
            g = last.get("guidance") or {}
            cols[side] = {"Tập hướng dẫn của phiên": nm(s.get("guides")),
                          "Hướng dẫn được truy hồi (chọn)": nm(g.get("selected")) if g.get("status") != "disabled" else "tắt (tập rỗng)",
                          "Đưa vào Jev": nm(g.get("supplied_to_planner")),
                          "Hành động Jev chọn": " → ".join(last.get("actions") or []) or "—",
                          "Công cụ được gọi": _tools_txt(last.get("tools") or []),
                          "Câu trả lời cho khách": last.get("agent_text") or "—",
                          "Thời gian phản hồi": f"{last.get('latency_ms')} ms (cả phiên {s.get('wall_ms')} ms)",
                          "Lỗi": s.get("error") or "—"}
        st.table([{"Cần xem": k, "Trước (không bản nháp)": cols["before"][k], "Sau (có bản nháp)": cols["after"][k]} for k in cols["before"]])
        w = [t for side in ("before", "after") for t in tr[side].get("writes") or []]
        if w:
            st.warning(f"Phiên thử có {len(w)} lệnh ghi (tạo / sửa đơn, hẹn gọi lại, chuyển máy) — chỉ trong môi trường thử, không phải giao dịch thật.")
        with st.expander(f"Toàn bộ lượt câu thử {i + 1} (gồm ngữ cảnh phát lại)"):
            for side, lab in (("before", "Trước"), ("after", "Sau")):
                st.markdown(f"**{lab}** · chế độ {tr[side].get('mode')}")
                for t in tr[side].get("turns") or []:
                    st.markdown(f"- {'(ngữ cảnh) ' if t.get('is_context') else ''}Khách: {t.get('customer_text')}  \n  Agent: {t.get('agent_text')}  \n"
                                f"  hành động: {' → '.join(t.get('actions') or []) or '—'} · tool: {_tools_txt(t.get('tools') or [])} · "
                                f"hướng dẫn đưa vào Jev: {nm((t.get('guidance') or {}).get('supplied_to_planner'))}")


def sandbox_panel(p, by, names):
    """18/11: so sánh trước / sau với Jev thật cho MỘT bản nháp (E.sandbox_run, tiến trình riêng). Bản nháp chỉ dùng trong phiên thử."""
    pid, pl = p["id"], p["payload"]
    if not st.checkbox("So sánh trước / sau với Jev thật", key=f"sbopen-{pid}"):
        return
    keys_ok = bool(BOOT.get("ok")) and all((BOOT.get("keys_present") or {}).values())
    with st.container(border=True):
        st.caption("Chạy luồng agent THẬT (bộ hiểu DeepSeek → truy hồi hướng dẫn → Jev chọn bước → tool → trả lời) hai phiên thử độc lập, "
                   "cùng ngữ cảnh và cấu hình: TRƯỚC = tập nền, SAU = tập nền + bản nháp này. Tiến trình riêng, DB / mock / trace riêng: "
                   "đơn tạo trong phiên thử không đụng cuộc gọi thật; bản nháp không được đóng gói hay kích hoạt.")
        if not keys_ok:
            st.warning("Cần khóa DeepSeek / TypeSafe và cấu hình khớp freeze (xem thanh bên) — chưa chạy được.")
        trials = lines(st.text_area("Câu khách thử (mỗi dòng một câu, tối đa 5) — nên có cách nói khác và một câu KHÔNG liên quan để kiểm tác dụng phụ",
                                    "\n".join((pl.get("examples") or [])[:2]), key=f"sb-{pid}-trials"))[:5]
        ctxs = E.sandbox_contexts()
        c1, c2 = st.columns([3, 1])
        sid = c1.selectbox("Ngữ cảnh: phát lại lời khách của một cuộc gọi trên UI (tùy chọn)", ["—"] + sorted(ctxs), key=f"sb-{pid}-ctx")
        ctx = []
        if sid != "—":
            turns = ctxs[sid]
            upto = c2.number_input("Số lượt đầu", 1, min(6, len(turns)), min(6, len(turns)), key=f"sb-{pid}-upto")
            ctx = [t for _, t in turns[: int(upto)]]
            st.caption("Phát lại ở cả hai phiên: " + " | ".join(ctx))
        b1, b2 = st.columns(2)
        base = b1.radio("Nền so sánh (TRƯỚC)", ["empty", "approved"], horizontal=True, key=f"sb-{pid}-base",
                        format_func=lambda x: "Không hướng dẫn (như R0)" if x == "empty" else "Các hướng dẫn đã duyệt")
        tt = b2.checkbox("B2-TT bật", value=True, key=f"sb-{pid}-tt")
        n_turns = len(trials) * 2 * (len(ctx) + 1)
        st.caption(f"Sẽ chạy {len(trials)} câu × 2 phiên × {len(ctx) + 1} lượt = {n_turns} lượt agent với model thật.")
        if st.button("So sánh trước / sau (Jev thật)", key=f"sbrun-{pid}", type="primary", disabled=not (by and keys_ok and trials)) \
                and by and keys_ok and trials:
            with st.spinner(f"đang chạy {n_turns} lượt agent thật trong tiến trình thử…"):
                rc, log, res, _ = E.sandbox_run(E.sandbox_spec(p, base, trials, ctx, tt, by))
            if rc != 0 or not res:
                st.error(f"Phiên thử lỗi (rc {rc}):\n\n{log}")
        hist = E.sandbox_history(pid)
        if hist:
            k = st.selectbox(f"Kết quả thử đã lưu ({len(hist)})", range(len(hist)), key=f"sb-{pid}-hist",
                             format_func=lambda i: f"{hist[i].get('at')} · {hist[i].get('by') or '—'} · {len(hist[i].get('trials') or [])} câu")
            show_compare(hist[k], names)


def guidance_flow():
    from core.config import settings
    from improve import store as S
    root, by = E.GUIDE_ROOT, st.session_state.get("reviewer", "")
    pend, appr, rej = [E.guidance_props(s) for s in ("pending", "approved", "rejected")]
    ga = E.guidance_active()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chờ duyệt", len(pend))
    m2.metric("Đã duyệt", len(appr))
    m3.metric("Đã loại", len(rej))
    m4.metric("Gói đang bật", os.path.basename(ga["package"]) if ga.get("package") else "—")
    st.caption("Hướng dẫn điều phối giúp Jev chọn cách xử lý: không phải lời nói với khách, không chứa giá, không cấp quyền giao dịch. "
               "Chỉ hướng dẫn ĐÃ DUYỆT và ĐÃ ĐÓNG GÓI mới tới agent, và chỉ cho cuộc gọi mở sau khi kích hoạt.")
    step = st.radio("Bước hướng dẫn", GSTEPS, horizontal=True, label_visibility="collapsed", key="g_step")
    caps = E.guide_capabilities()

    if step == GSTEPS[0]:
        fbs = [json.loads(l) for l in open(E.FEEDBACK, encoding="utf-8") if l.strip()] if os.path.exists(E.FEEDBACK) else []
        bad = [f for f in fbs if f.get("rating") == -1]
        st.markdown(f"**Đánh giá của nhân viên:** {len(fbs)} lượt, {len(bad)} “Cần cải thiện”")
        if bad:
            st.dataframe([{"lúc": f.get("at"), "người": f.get("by"), "chế độ": f.get("mode"), "khách": f.get("customer_text"),
                           "agent": f.get("agent_text"), "ghi chú": f.get("note")} for f in bad[-30:]], width="stretch")
        st.caption("Bản nháp do trợ lý soạn ngoài UI từ feedback này và dev được phép đọc (tải ui_data.zip ở thanh bên để chuyển "
                   "feedback), rồi nhập vào đây. Nhập chỉ đưa vào HÀNG CHỜ DUYỆT, chưa tới agent.")
        files = sorted(f for f in os.listdir(root) if f.startswith("drafts") and f.endswith(".json")) if os.path.isdir(root) else []
        up = st.file_uploader("Tệp nháp (JSON)", type=["json"], key="g_upload")
        pick = st.selectbox("Hoặc bản nháp có sẵn trong kho", ["—"] + files, key="g_pick")
        author = st.text_input("Người / model soạn nháp", "", key="g_author")
        if st.button("Nhập vào hàng chờ duyệt", type="primary", disabled=not (author.strip() and (up is not None or pick != "—"))):
            if up is not None:
                data = up.getvalue()
                os.makedirs(os.path.join(root, "imports"), exist_ok=True)
                path = os.path.join(root, "imports", f"{hashlib.sha1(data).hexdigest()[:10]}_{os.path.basename(up.name)}")
                with open(path, "wb") as fh:
                    fh.write(data)
            else:
                path = os.path.join(root, pick)
            rc, out = run_cmd(["import", "--root", root, "--drafts", path, "--author", author.strip()])
            (st.success if rc == 0 else st.error)(out[-3000:])

    elif step == GSTEPS[1]:
        if not by:
            st.info("Nhập tên nhân viên ở thanh bên để duyệt.")
        st.caption("Duyệt TỪNG hướng dẫn sau khi đọc điều kiện, ngoại lệ và test. Loại phải ghi lý do. Duyệt chưa có hiệu lực: phải đóng "
                   "gói và kích hoạt ở bước 3. Sửa nội dung → lưu thành phiên bản nháp mới (không sửa tại chỗ bản đã duyệt / đã đóng gói).")
        if st.session_state.get("g_flash"):
            st.success(st.session_state.pop("g_flash"))
        everyone = [E.guide_dto(p) for p in pend + appr]
        names = _names(pend, appr, rej)
        from improve import guidance_edit as GE
        for p in pend:
            with st.container(border=True):
                guide_card(p, caps)
                errs = S.validate(p)
                if errs:
                    st.error("Không hợp lệ: " + "; ".join(errs))
                tk = f"gt-{p['id']}"
                if st.button("Chạy test của hướng dẫn này", key=f"run-{p['id']}", disabled=not p.get("tests")):
                    st.session_state[tk] = E.run_guide_tests(p["id"], everyone, p.get("tests"))
                res = st.session_state.get(tk)
                if res:
                    (st.success if all(r["pass"] for r in res) else st.warning)(
                        f"{sum(r['pass'] for r in res)}/{len(res)} test đạt (trên kho chờ duyệt + đã duyệt)")
                    st.dataframe([{"test": r["test"], "kỳ vọng": r["expect"], "được chọn": r["selected"], "đạt": r["pass"],
                                   "hướng dẫn được chọn": ", ".join(r["chosen"]), "điểm": json.dumps(r["scores"])} for r in res],
                                 width="stretch")
                sandbox_panel(p, by, names)
                edit_panel(p, by, root)
                reason = st.text_input("Lý do (bắt buộc khi loại)", key=f"gr-{p['id']}")
                a1, a2, _ = st.columns([2, 2, 6])
                try:
                    # điều kiện kiểm lại phía server: nút bị vô hiệu chỉ là ràng buộc phía trình duyệt
                    if a1.button("Duyệt hướng dẫn này", key=f"ga-{p['id']}", disabled=not by or bool(errs), type="primary") \
                            and by and not errs:
                        _, sup = GE.approve(p["id"], by, reason, root=root)     # bản đã duyệt cũ cùng guide_id → Đã loại (thay thế)
                        if sup:
                            st.session_state["g_flash"] = f"Đã duyệt {p['id']}; bản cũ {', '.join(sup)} chuyển sang Đã loại (thay thế)."
                        st.rerun()
                    if a2.button("Loại", key=f"gx-{p['id']}", disabled=not (by and reason.strip())) and by and reason.strip():
                        S.reject(p["id"], by, reason, root=root)
                        st.rerun()
                except S.ProposalError as e:
                    st.error(str(e))
        if not pend:
            st.caption("Không có hướng dẫn chờ duyệt.")
        st.markdown(f"**Đã duyệt ({len(appr)})** — sẽ vào gói đóng ở bước 3")
        for p in appr:
            with st.container(border=True):
                rv = p.get("review") or {}
                st.markdown(f"**{p['payload'].get('title')}** v{p['payload'].get('version')} ({p['id']}) — duyệt bởi {rv.get('by')} lúc "
                            f"{rv.get('at')}: {rv.get('reason') or ''}")
                if st.button("Đưa về chờ duyệt", key=f"go-{p['id']}", disabled=not by) and by:
                    S.reopen(p["id"], by, "đưa về chờ duyệt từ UI", root=root)
                    st.rerun()
                edit_panel(p, by, root)
        dup = GE.approved_duplicates(root)
        if dup:
            st.error(f"Nhiều phiên bản cùng hướng dẫn đang ở “Đã duyệt” {dup} — đóng gói sẽ bị từ chối; đưa bản cũ về chờ duyệt hoặc loại.")
        if rej:
            st.markdown(f"**Đã loại ({len(rej)})**")
            for p in rej:
                rv = p.get("review") or {}
                st.caption(f"{p['payload'].get('title')} ({p['id']}) — {rv.get('by')}: {rv.get('reason')}")

    elif step == GSTEPS[2]:
        st.caption("Gói = bản đóng băng của MỌI hướng dẫn đang ở “Đã duyệt” (muốn bỏ một cái thì đưa về chờ duyệt trước). Gói bất biến: "
                   "sửa nội dung → duyệt lại → gói mới. Kích hoạt chỉ áp dụng cho cuộc gọi mở sau; đo R0 / R1 truyền đường dẫn gói tường minh.")
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Tên gói mới", "", placeholder="vd r1", key="g_pkg_name")
        if c2.button("Đóng gói hướng dẫn đã duyệt", disabled=not (by and name.strip() and appr)) and by and name.strip() and appr:
            out = os.path.join(E.GUIDE_PKGS, name.strip())
            rc, txt = run_cmd(["package", "--root", root, "--name", name.strip(), "--by", by, "--out", out])
            (st.success if rc == 0 else st.error)(txt[-2000:])
            if rc == 0:
                st.session_state[f"reg-{name.strip()}"] = run_cmd(["regress", "--pkg", out])
        pkgs = E.guidance_packages()
        if not pkgs:
            st.caption("Chưa có gói nào.")
            return
        sel = st.selectbox("Gói", range(len(pkgs)), key="g_pkg_sel",
                           format_func=lambda i: f"{pkgs[i]['name']} · {pkgs[i]['meta'].get('n')} hướng dẫn · hash "
                                                 f"{pkgs[i]['meta'].get('approved_hash')} · {pkgs[i]['meta'].get('by')} {pkgs[i]['meta'].get('at')}")
        pk = pkgs[sel]
        try:
            st.markdown("**Trong gói:** " + "; ".join(g.get("title") or g["id"] for g in E.package_guides(pk["path"])))
        except Exception as e:  # noqa: BLE001 — gói sai thì agent cũng từ chối mở phiên
            st.error(f"Gói không nạp được (agent sẽ từ chối mở phiên): {e}")
        if st.button("Chạy regress gói này"):
            st.session_state[f"reg-{pk['name']}"] = run_cmd(["regress", "--pkg", pk["path"]])
        reg = st.session_state.get(f"reg-{pk['name']}")
        if reg:
            (st.success if reg[0] == 0 else st.error)(("regress đạt" if reg[0] == 0 else "regress TRƯỢT") + "\n\n" + reg[1][-2000:])
        reason = st.text_input("Lý do kích hoạt / quay lui", "", key="g_act_reason")
        d1, d2, _ = st.columns([3, 2, 5])
        if d1.button("Kích hoạt cho cuộc gọi mở sau", disabled=not by, type="primary") and by:
            reg = run_cmd(["regress", "--pkg", pk["path"]])
            st.session_state[f"reg-{pk['name']}"] = reg
            if reg[0] != 0:
                st.error("Regress trượt — không kích hoạt.")
            else:
                rc, txt = run_cmd(["activate", "--pkg", pk["path"], "--by", by, "--reason", reason, "--state", E.GUIDE_STATE])
                (st.success if rc == 0 else st.error)(txt[-1500:])
        if d2.button("Quay lui gói trước", disabled=not by) and by:
            rc, txt = run_cmd(["rollback", "--by", by, "--reason", reason, "--state", E.GUIDE_STATE])
            (st.success if rc == 0 else st.error)(txt[-1500:])
        logp = os.path.join(E.GUIDE_STATE, "activation_log.jsonl")
        if os.path.exists(logp):
            st.markdown("**Nhật ký kích hoạt / quay lui**")
            st.table([json.loads(l) for l in open(logp, encoding="utf-8") if l.strip()][-8:])

    else:
        from harness.understanding import ASKS
        st.caption("Truy hồi thật trên một tập hướng dẫn, ngoài cuộc gọi, không gọi model: xem hướng dẫn nào được chọn hoặc bị áp nhầm. "
                   f"Ngưỡng điểm hiện tại {settings.guidance_min_score} là giá trị TẠM, chưa hiệu chỉnh.")
        pkgs = E.guidance_packages()
        srcs = ["Kho: chờ duyệt + đã duyệt"] + [f"Gói {p['name']}" for p in pkgs]
        src = st.selectbox("Tập hướng dẫn", range(len(srcs)), format_func=lambda i: srcs[i], key="g_try_src")
        text = st.text_input("Khách nói", "", key="g_try_text")
        c1, c2, c3 = st.columns(3)
        asked = c1.selectbox("Nhân viên vừa hỏi (slot)", SLOTS_ASKED, format_func=lambda x: x or "—", key="g_try_slot")
        asks = c2.multiselect("Khách hỏi về (asks)", sorted(ASKS), key="g_try_asks")
        two = c3.checkbox("B2-TT bật", value=True, key="g_try_tt")
        s1, s2 = st.columns(2)
        sort = s1.selectbox("Tiêu chí tư vấn", ["none", "cheapest", "most_expensive"], key="g_try_sort")
        span = s2.text_input("Nhóm hàng khách nêu", "", key="g_try_span")
        if st.button("Thử truy hồi", type="primary", disabled=not text.strip()):
            try:
                guides = [E.guide_dto(p) for p in pend + appr] if src == 0 else E.package_guides(pkgs[src - 1]["path"])
                consult = {"sort": sort, "category_span": span.strip() or None} if (sort != "none" or span.strip()) else None
                tr = E.try_retrieval(guides, text, asked or None, asks, two, consult)["trace"]
                names = {g["id"]: g.get("title") for g in guides}
                st.markdown(f"**Trạng thái:** {tr.get('status')} · chọn {len(tr.get('selected') or [])} · token ước tính {tr.get('tokens_est')}")
                if tr.get("candidates"):
                    st.dataframe([{"hướng dẫn": names.get(c["id"], c["id"]), "điểm": c["score"],
                                   "được chọn": c["id"] in (tr.get("selected") or []), "lý do lọc": (tr.get("filtered") or {}).get(c["id"], "")}
                                  for c in tr["candidates"]], width="stretch")
                else:
                    st.caption("Không hướng dẫn nào khớp.")
            except Exception as e:  # noqa: BLE001
                st.error(f"{type(e).__name__}: {e}")


with tab_improve:
    if E.CANDIDATE:
        guidance_flow()
        st.divider()
        if st.checkbox("Xem luồng FAQ cũ (đã dừng mở rộng)", key="show_faq"):
            faq_flow()
    else:
        faq_flow()
