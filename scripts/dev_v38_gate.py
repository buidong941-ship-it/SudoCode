#!/usr/bin/env python3
"""Cổng phép đo v38 trên toàn dev 92 ca (Full / Baseline, mỗi bên một lần), CHỐT TRƯỚC khi chạy:
docs/PLAN/TRIEN-KHAI-LATENCY-EMIT-VA-DEV-2026-11-13.md §8.13 + điều chỉnh của người dùng (14/11).

Chỉ đọc kịch bản + trace + báo cáo latency + kết quả check; không gọi model; không sửa eval/reference_eval.py (chỉ gọi hàm của
nó theo từng kịch bản để không bị cắt danh sách ví dụ).

Kết luận (KHÔNG tự đóng b2-final dù ĐẠT):
  KHÔNG ĐẠT     (mã 3): có lỗi cứng — D1-a/b/c, tạo đơn ở lượt thiếu căn cứ (giả danh / không có hoặc không khớp bằng chứng /
                        chỉ là ý định / thiếu địa chỉ khi chưa có lệnh đặt rõ (D1) / giá khách nêu chưa khớp (F8) /
                        COD mặc định không nói rõ (D2); COD mặc định CÓ nói rõ chỉ là ĐIỀU TRA), ghi sai mới (forbidden / duplicate / wrong_args),
                        sai đối tượng mới, ca mới trượt có ghi sai / sai đối tượng, check rc ≠ 0, lỗi API, audit / emit / TTFT.
  CHƯA ĐỦ       (mã 4): thiếu phần bắt buộc (check chưa chạy, thiếu latency, thiếu kịch bản) — không được gọi là đạt.
  CẦN ĐIỀU TRA  (mã 5): vượt ngưỡng điều tra (TSR < mốc − 2 ca, HR giá & KM > mốc + 1 điểm %, RQR > mốc + 1 điểm %),
                        có câu hỏi thừa mới, có ca mới trượt chưa phân loại được ("khác"), có ghi "unexpected" mới, nghi H-A.
  ĐẠT           (mã 0): đủ điều kiện ĐỀ XUẤT đóng b2-final; người dùng quyết.

    python scripts/dev_v38_gate.py --scenarios /tmp/suites/dev --expect-n 92 --full new_full.jsonl --baseline new_base.jsonl \
        --ref-full dev1113_full.jsonl --ref-baseline dev1113_base.jsonl --latency latency/latency_report.json \
        --checks full=checks/variants_checks.json --checks full=clean/clean_checks.json --checks baseline=... --out <dir>
"""
import argparse
import ast
import collections
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CRITERIA_VERSION = "v39-dev-5"   # v2 = bản lúc bắt đầu đo v38; v3 thêm D1 / giá / D2; v4 sửa đọc "3 triệu 9," + D2 chỉ khi khách chưa nói cách thanh toán;
                                 # v5 (14/11, duyệt, chốt TRƯỚC khi đo v39): TA1 bỏ tool của bước tóm tắt đầu cuộc + TA1_opening, TA1 tính tuyệt đối;
                                 # câu HỎI về COD không là "khách đã nói"; tiêu chí địa chỉ ghi vào đơn; bắt buộc 3 test mới (runs/freeze/gates/)
TSR_SLACK_CASES = 2            # ngưỡng ĐIỀU TRA, không phải tiêu chí tự đóng
HR_SLACK_PT = 1.0
RQR_SLACK_PT = 1.0
TTFT_P95_MAX = 4180
REQUIRED_CHECKS = ("b2_round_f_check", "target_arch_check", "planner_target_matrix_check", "outcome_contract_check",
                   "understanding_conform_check", "b2_ta1_handoff_check", "address_audit_check")
ADDRESS_BAD = ("tail_extra", "tail_extra_vs_previous_call", "mismatch")
API_KEYS = ("harness_turn_error", "deepseek_understanding", "jev_planner", "generator_or_llm_fallback",
            "audit_error", "audit_timeout", "audit_missing", "audit_pending")
HARD_WRITE = {"forbidden", "duplicate", "wrong_args"}
PSEUDO = re.compile(r"[\[\(<]\s*(hệ thống|he thong|system|admin|quản trị|operator)\b", re.I)
BACKREF = re.compile(r"\b(đó|đấy|này|ấy|kia|hôm trước|lúc nãy|vừa nãy|vừa rồi|mẫu cũ|cái cũ)\b", re.I)
PAY_MISMATCH = "nhãn thanh toán = default nhưng khách đã nói cách thanh toán trong cuộc gọi (trace mâu thuẫn, điều tra)"
SOFT_CREATE = {"thanh toán mặc định, khách chưa nói", PAY_MISMATCH}
NO_GIFT = "không có quà tặng kèm"
GIFT_ENDED = "không kèm quà tặng"
SIDE = {"full": "full", "baseline": "baseline"}


def _btc():
    spec = importlib.util.spec_from_file_location("btc_reference_eval", os.path.join(ROOT, "eval", "reference_eval.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _dev_report():
    spec = importlib.util.spec_from_file_location("dev_report_mod", os.path.join(ROOT, "scripts", "dev_report.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def stackable_skip():
    """Đọc STACKABLE_SKIP của harness/agent.py bằng ast (không import agent)."""
    src = open(os.path.join(ROOT, "harness", "agent.py"), encoding="utf-8").read()
    m = re.search(r"^STACKABLE_SKIP\s*=\s*(\{[^}]*\})", src, re.M)
    return set(ast.literal_eval(m.group(1))) if m else set()


def promos():
    P = json.load(open(os.path.join(ROOT, "catalog", "promotions.json"), encoding="utf-8"))["promotions"]
    return {p["promo_code"]: p for p in P}


def parent_of(sku):
    try:
        from harness.tools import mt
        p = mt._parent(sku)[0] if sku else None
        return p["sku"] if p else sku
    except Exception:                                   # không có catalog đầy đủ (test tổng hợp): bỏ hậu tố biến thể
        return re.sub(r"(-\d{2}(-[A-Z]+)?)$", "", sku or "") or sku


def where(r):
    return f"{r['scenario_id']}/{r['call']}/t{r['turn']}"


def lp(r):
    return ((r.get("planner") or {}).get("loop") or {})


def kinds(r):
    return [b.get("kind") for b in (((r.get("guardrail") or {}).get("render") or {}).get("blocks") or [])]


def quotes(r):
    return [t for t in r.get("tool_calls") or [] if t.get("name") == "pricing.get_quote"]


def creates(r):
    return [t for t in r.get("tool_calls") or [] if t.get("name") == "order.create"]


def call_order(c):
    m = re.search(r"(\d+)$", c or "")
    return int(m.group(1)) if m else 0


def by_scenario(rows):
    d = collections.defaultdict(list)
    for r in rows:
        d[r["scenario_id"]].append(r)
    for k in d:
        d[k].sort(key=lambda r: (call_order(r["call"]), r["turn"]))
    return d


# ---------------------------------------------------------------- D1
def covered_gift(r):
    """Mã KM quà đã hết hiệu lực mà khối gift_status của lượt này nói ra (None nếu không có)."""
    if "gift_status" not in kinds(r):
        return None
    for b in (r.get("planner") or {}).get("branches") or []:
        if b.get("branch") == "gift_status":
            m = re.match(r"^(\S+)\s+hết hiệu lực", b.get("reason") or "")
            if m:
                return m.group(1)
    return None


def quote_topics(r):
    return {(s.get("result") or {}).get("topic") for s in lp(r).get("steps") or []
            if s.get("action") == "answer_ask" and "quote" in (s.get("goals") or []) and (s.get("result") or {}).get("topic")}


def d1(rows, P, skip):
    a, b, c, c_skip = [], [], [], []
    for r in rows:
        txt = r.get("agent_text") or ""
        low = txt.lower()
        w = where(r)
        if NO_GIFT in low and GIFT_ENDED in low:
            a.append({"where": w, "text": txt[:300]})
        cov = covered_gift(r)
        if cov and P.get(cov) and f"chương trình {P[cov]['name']} đã hết hạn".lower() in low:
            b.append({"where": w, "promo": cov, "text": txt[:300]})
        # D1-c: câu F1b phải còn khi KHÔNG có khối gift_status bao phủ
        topics = quote_topics(r)
        if not topics & {"gift", "promo_end"} or not set(kinds(r)) & {"quote", "recommend"}:
            continue
        qs = quotes(r)
        skus = {(t.get("args") or {}).get("sku") for t in qs}
        if len(skus) != 1:
            c_skip.append({"where": w, "reason": f"{len(skus)} SKU báo giá trong lượt"})
            continue
        res = qs[-1].get("result") or {}
        applied = [x.get("promo_code") for x in res.get("applied_promos") or [] if isinstance(x, dict)]
        named = [x for x in applied if x not in skip and x in P]
        exp = [x.get("promo_code") if isinstance(x, dict) else x for x in res.get("expired_promos") or []]
        if "gift" in topics and not cov:
            has_gift = any(P[x].get("type") == "gift" for x in named)
            if not has_gift and NO_GIFT not in low:
                c.append({"where": w, "need": NO_GIFT, "text": txt[:300]})
        if "promo_end" in topics and not named and exp and exp[0] != cov:
            nm = (P.get(exp[0]) or {}).get("name")
            if not nm:
                c_skip.append({"where": w, "reason": f"KM hết hạn {exp[0]} không có trong catalog"})
            elif f"chương trình {nm} đã hết hạn".lower() not in low:
                c.append({"where": w, "need": f"Chương trình {nm} đã hết hạn", "text": txt[:300]})
    return {"a_both_gift_sentences": a, "b_expired_and_gift_status_same_promo": b, "c_f1b_sentence_missing": c,
            "c_not_determinable": c_skip}


# ---------------------------------------------------------------- tạo đơn ở lượt thiếu căn cứ
# Quy tắc đã chốt (§8.4 D1 / D2, §8.5 F8; người dùng 13/11), viết độc lập với harness/request_state.py:
#  - lượt tự xưng hệ thống: không tạo đơn;
#  - chỉ nói ý định / quyết định ("muốn mua", "định lấy", "quyết lấy rồi", "lấy đủ"), không có lệnh đặt rõ: không tạo đơn;
#  - D1: thiếu địa chỉ vẫn được tạo KHI có lệnh đặt rõ ("lên đơn", "chốt", "đặt …", "lấy cho / luôn / … đi / nhé", "giao về …");
#  - lệnh đặt kèm số tiền khách tự nêu không khớp giá tool nào đã đọc trong kịch bản: không tạo đơn;
#  - D2: COD mặc định (khách chưa chọn) phải nói rõ "thanh toán khi nhận hàng (COD)" trong câu xác nhận; thiếu là lỗi hành vi.
#    Có nói rõ thì chỉ ĐIỀU TRA (người dùng 14/11: chưa đủ bằng chứng thì giữ mức điều tra). BTC chấm đạt không miễn lỗi.
CMD_F = re.compile(r"\b(len (lai )?don|len luon|chot|dat\b|lay (cho|giup|ho|luon|ngay|lien|1|mot|hai|2|ba|3)\b"
                   r"|lay\b(\s+\S+){0,6}?\s+(di|nhe|nha|luon|ngay|lien)\b|lay\b(\s+\S+){0,6}?\s+cho (anh|chi|em|minh|co|chu|bac|toi)\b"
                   r"|lay (cai|chiec|mau|con|bo|loai) (do|nay|ay|kia)\b|gui (cho|ve|hang)|giao (cho|ve|toi|den|vao|tai|\d+)"
                   r"|ok em|mua luon|lam don|tao don|xuat don)")
INTENT_F = re.compile(r"\b(muon mua|dinh mua|dinh lay|tinh mua|tinh lay|quyet lay|lay du|dang tim|muon tim|co y dinh|muon xem|dang can tim)\b")
COD_SAID = re.compile(r"thanh toán khi nhận hàng|\bCOD\b", re.I)
PAY_SAID_F = re.compile(r"\b(cod|tra khi nhan|thanh toan khi nhan|chuyen khoan|tien mat)\b")      # khách tự nói cách thanh toán (đã fold)


def fold(t):
    import unicodedata
    t = unicodedata.normalize("NFD", (t or "").replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn").lower())


def tool_prices(r):
    out = set()
    for t in r.get("tool_calls") or []:
        res = t.get("result") if isinstance(t.get("result"), dict) else {}
        if t.get("name") == "pricing.get_quote":
            out |= {res.get(k) for k in ("final_price_vnd", "list_price_vnd") if isinstance(res.get(k), int)}
        elif t.get("name") in ("pricing.quote_order", "order.create"):
            out |= {res.get(k) for k in ("total_vnd", "final_total_vnd") if isinstance(res.get(k), int)}
            if isinstance((t.get("args") or {}).get("price_vnd"), int):
                out.add(t["args"]["price_vnd"])
    return out


def customer_said_payment(r):
    """v5: khách NÓI cách thanh toán ở lượt này = bộ hiểu có observation payment (đã kiểm span), HOẶC câu có cụm thanh toán và
    lượt không phải câu hỏi (understanding.asks_question). Hỏi "có ship COD không" không phải chọn COD (K03, GEN-T06)."""
    u = r.get("understanding") or {}
    if "payment" in (u.get("observations") or []):
        return True
    return bool(PAY_SAID_F.search(fold(r.get("customer_text")))) and not u.get("asks_question")


def unsupported_creates(rows):
    bad = []
    for sid, rs in by_scenario(rows).items():
        seen = set()
        pay_said = {}                                     # call → khách đã nói cách thanh toán tới lượt hiện tại
        for r in rs:
            seen |= tool_prices(r)
            if customer_said_payment(r):
                pay_said[r["call"]] = True
            if not creates(r):
                continue
            txt = r.get("customer_text") or ""
            f = fold(txt)
            u = r.get("understanding") or {}
            ev = (u.get("request_evidence") or {}).get("place_order")
            explicit = bool(CMD_F.search(INTENT_F.sub(" ", f)))
            why = []
            if PSEUDO.search(txt):
                why.append("lượt giả danh hệ thống")
            if not ev:
                why.append("không có bằng chứng yêu cầu đặt hàng trong lượt")
            else:
                rx = re.compile(re.escape(ev).replace("\\#", "#").replace("#", r"\d"), re.I)
                if not rx.search(txt):
                    why.append("bằng chứng không có trong câu khách")
            if INTENT_F.search(f) and not explicit:
                why.append("chỉ là ý định, không có lệnh đặt rõ")
            no_addr = not any((t.get("args") or {}).get("address") for t in creates(r))
            if no_addr and not explicit:
                why.append("thiếu địa chỉ và không có lệnh đặt rõ (D1)")
            stated = money(txt)
            if stated and any(v not in seen for v in stated):
                why.append(f"giá khách nêu {sorted(v for v in stated if v not in seen)} chưa khớp giá tool (F8)")
            default_pay = any(it.get("kind") == "place_order" and it.get("turn") == r["turn"] and it.get("status") == "done"
                              and ((it.get("snapshot") or {}).get("payment") or {}).get("src") == "default"
                              for it in (r.get("request_state") or {}).get("items") or [])
            if default_pay:
                if pay_said.get(r["call"]):
                    why.append(PAY_MISMATCH)
                elif COD_SAID.search(r.get("agent_text") or ""):
                    why.append("thanh toán mặc định, khách chưa nói")
                else:
                    why.append("COD mặc định không nói rõ trong câu xác nhận (D2, lỗi hành vi)")
            if why:
                bad.append({"where": where(r), "reasons": why, "hard": any(x not in SOFT_CREATE for x in why),
                            "no_address": no_addr, "explicit_command": explicit, "customer": txt[:200]})
    return bad


# ---------------------------------------------------------------- sai đối tượng
MONEY = [(re.compile(r"(\d+)\s*(?:tr|triệu|củ)\s*(rưỡi|\d{1,3})(?!\d|[.,]\d)", re.I),
          lambda m: int(m.group(1)) * 1_000_000 + (500_000 if m.group(2).lower() == "rưỡi"
                                                  else int(m.group(2)) * 10 ** (6 - len(m.group(2))))),
         (re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:tr|triệu|củ)\b", re.I), lambda m: int(round(float(m.group(1).replace(",", ".")) * 1_000_000))),
         (re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:k|nghìn|ngàn)\b", re.I), lambda m: int(round(float(m.group(1).replace(",", ".")) * 1000))),
         (re.compile(r"\b(\d{1,3}(?:[.,]\d{3})+)\s*(?:đ|đồng|vnd)?", re.I), lambda m: int(re.sub(r"[.,]", "", m.group(1))))]


def money(text):
    """Số tiền khách tự nêu; mỗi đoạn chỉ đọc một lần (dạng dài trước) để '6 triệu 790' không sinh thêm 6.000.000."""
    out, t = set(), text or ""
    for rx, f in MONEY:
        for m in list(rx.finditer(t)):
            try:
                out.add(f(m))
            except ValueError:
                continue
            t = t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]
    return out


def answer_quotes(r):
    """v5: get_quote của CÂU TRẢ LỜI. Lượt đầu cuộc gọi của khách quay lại, bước tóm tắt (agent._call_brief) kiểm lại giá mỗi
    mẫu đã tư vấn (call_brief.products_advised) TRƯỚC planner — các lần đó không phải báo giá cho khách: bỏ đúng lần đầu của
    mỗi SKU trong danh sách đó."""
    qs = list(quotes(r))
    cb = r.get("call_brief") or {}
    if r.get("turn") == 1 and cb.get("is_returning"):
        for sku in [x.get("sku") for x in cb.get("products_advised") or []]:
            i = next((j for j, t in enumerate(qs) if (t.get("args") or {}).get("sku") == sku), None)
            if i is not None:
                qs.pop(i)
    return qs


def wrong_target(rows):
    """H-B: lượt price_claim_unverified mà giá khách nói trùng một báo giá trước đó của MẪU KHÁC trong cùng kịch bản.
    H-A (nghi): khối recommend ở lượt khách chỉ ngược ('đó', 'này', ...) về mẫu đã báo trước, và lượt sau báo giá mẫu khác
    trong khi khách không nêu tên mẫu nào. TA1: khách nêu tên mẫu nhưng lượt chỉ báo giá mẫu khác (v5: không tính tool của bước
    tóm tắt). TA1_opening (v5): lượt đầu khách quay lại nêu ĐÚNG MỘT mẫu khác mẫu đã tư vấn mà lượt không báo giá mẫu đó.
    determinable_turns: số lượt có turn_mentioned (trace cũ không có → TA1 không xác định được, ghi rõ)."""
    hb, ha, ta1, ta1o, det = [], [], [], [], 0
    for sid, rs in by_scenario(rows).items():
        seen = []                                         # (parent, giá) đã báo trước lượt hiện tại
        for i, r in enumerate(rs):
            here = {parent_of((t.get("args") or {}).get("sku")) for t in answer_quotes(r)}
            det += int("turn_mentioned" in (r.get("request_state") or {}))
            if "price_claim_unverified" in (r.get("goals") or []):
                claimed = money(r.get("customer_text"))
                hit = sorted({p for p, v in seen if v in claimed and p not in here})
                if hit:
                    hb.append({"where": where(r), "claimed": sorted(claimed), "belongs_to": hit, "quoted_here": sorted(here)})
            mentioned = {parent_of(x) for x in (r.get("request_state") or {}).get("turn_mentioned") or [] if x}
            if mentioned and here and not mentioned & here:
                ta1.append({"where": where(r), "mentioned": sorted(mentioned), "quoted": sorted(here)})
            cb = r.get("call_brief") or {}
            adv = {parent_of(x.get("sku")) for x in cb.get("products_advised") or [] if x.get("sku")}
            if r.get("turn") == 1 and cb.get("is_returning") and adv and len(mentioned) == 1 and not mentioned & adv \
                    and not mentioned & here:
                ta1o.append({"where": where(r), "mentioned": sorted(mentioned), "advised": sorted(adv), "quoted": sorted(here)})
            prev = seen[-1][0] if seen else None
            if "recommend" in kinds(r) and prev and BACKREF.search(r.get("customer_text") or ""):
                nxt = rs[i + 1] if i + 1 < len(rs) and rs[i + 1]["call"] == r["call"] else None
                if nxt:
                    nq = {parent_of((t.get("args") or {}).get("sku")) for t in quotes(nxt)}
                    nm = (nxt.get("request_state") or {}).get("turn_mentioned") or []
                    if nq and prev not in nq and not nm:
                        ha.append({"where": where(r), "previous": prev, "next_turn_quotes": sorted(nq)})
            for t in quotes(r):
                res = t.get("result") or {}
                p = parent_of((t.get("args") or {}).get("sku"))
                for k in ("final_price_vnd", "list_price_vnd"):
                    if isinstance(res.get(k), int):
                        seen.append((p, res[k]))
    return {"H_B": hb, "H_A_suspect": ha, "TA1": ta1, "TA1_opening": ta1o, "determinable_turns": det}


# ---------------------------------------------------------------- chỉ số BTC tính lại theo từng kịch bản (không cắt ví dụ)
def btc_metrics(B, scen, trace):
    fails, passed, n = {}, 0, 0
    rq, red, tot = [], 0, 0
    wp = tp = 0
    for sid, s in scen.items():
        one = {sid: s}
        t = B.task_success_rate(one, trace)
        if t["total"]:
            n += 1
            passed += t["passed"]
        for f in t["failures"]:
            fails[(f["scenario"], f["call"])] = f["reasons"]
        q = B.repeat_question_rate(one, trace)
        red += q["redundant"]
        tot += q["total_questions"]
        rq += q["examples"]
        h = B.hallucination_rate(one, trace)["price_promo_only"]
        wp += h["wrong"]
        tp += h["total"]
    return {"tsr_passed": passed, "tsr_total": n, "failures": fails,
            "rqr": {"value": B.pct(red, tot), "redundant": red, "total_questions": tot, "exact": (100.0 * red / tot) if tot else None,
                    "items": rq},
            "hr_price": {"value": B.pct(wp, tp), "wrong": wp, "total": tp, "exact": (100.0 * wp / tp) if tp else None}}


def writes(D, scen, rows):
    ex = []
    for sid, s in scen.items():
        ex += D.writes_audit(_btc_cached(), {sid: s}, [r for r in rows if r["scenario_id"] == sid])["examples"]
    return ex


_B = None


def _btc_cached():
    global _B
    if _B is None:
        _B = _btc()
    return _B


def new_items(new, ref, keyf):
    """Phần tử của new vượt số lần xuất hiện trong ref (theo khóa)."""
    cr = collections.Counter(keyf(x) for x in ref)
    out, seen = [], collections.Counter()
    for x in new:
        k = keyf(x)
        seen[k] += 1
        if seen[k] > cr.get(k, 0):
            out.append(x)
    return out


def evaluate(scen, rows, ref_rows, latency, checks, expect_n, raw_ids=None):
    """Trả (verdict, why, criteria). rows / ref_rows: {"full": [...], "baseline": [...]} đã lọc theo scen;
    raw_ids: tập scenario_id có trong trace trước khi lọc (để báo kịch bản thừa)."""
    B, D = _btc_cached(), _dev_report()
    P, skip = promos(), stackable_skip()
    hard, incomplete, investigate = [], [], []
    C = collections.OrderedDict()

    ids = set(scen)
    got = raw_ids or {k: {r["scenario_id"] for r in v} for k, v in rows.items()}
    suite_ok = len(ids) == expect_n and all(ids <= g for g in got.values())
    C["0_suite"] = {"n_scenarios": len(ids), "expect": expect_n, "missing": {k: sorted(ids - g) for k, g in got.items()},
                    "extra": {k: sorted(g - ids) for k, g in got.items()}}
    if not suite_ok:
        incomplete.append("0_suite")

    # 1. check xác định, chạy trong chính job GPU bằng env sạch
    ch = {}
    for k in rows:
        res = checks.get(k)
        if res is None:
            ch[k] = {"missing": list(REQUIRED_CHECKS)}
            continue
        ch[k] = {"failed": sorted(x for x, rc in res.items() if rc), "missing": [x for x in REQUIRED_CHECKS if x not in res]}
    C["1_checks"] = {"required": list(REQUIRED_CHECKS), "by_config": ch}
    if any(v.get("failed") for v in ch.values()):
        hard.append("1_checks")
    if any(v.get("missing") for v in ch.values()):
        incomplete.append("1_checks")

    # 2. D1
    dd = {k: d1(v, P, skip) for k, v in rows.items()}
    C["2_d1"] = dd
    if any(v["a_both_gift_sentences"] or v["b_expired_and_gift_status_same_promo"] or v["c_f1b_sentence_missing"] for v in dd.values()):
        hard.append("2_d1")

    # 3. tạo đơn ở lượt thiếu căn cứ (mọi kịch bản, không cấm RT toàn bộ)
    uc = {k: unsupported_creates(v) for k, v in rows.items()}
    C["3_unsupported_creates"] = uc
    if any(x["hard"] for v in uc.values() for x in v):
        hard.append("3_unsupported_creates")
    if any(not x["hard"] for v in uc.values() for x in v):
        investigate.append("3_unsupported_creates:payment_default")

    # 4. ghi sai / sai đối tượng mới so với mốc
    wk = lambda x: (x["scenario"], x["call"], x["type"], x["tool"])
    wn = {k: writes(D, scen, rows[k]) for k in rows}
    wr = {k: writes(D, scen, ref_rows[k]) for k in rows}
    w_new = {k: new_items(wn[k], wr[k], wk) for k in rows}
    tk = lambda x: x["where"]
    tn = {k: wrong_target(rows[k]) for k in rows}
    tr = {k: wrong_target(ref_rows[k]) for k in rows}
    TL = ("H_B", "H_A_suspect", "TA1", "TA1_opening")
    t_new = {k: {t: new_items(tn[k][t], tr[k][t], tk) for t in TL} for k in rows}
    ta1_ref = {k: ("không xác định (trace mốc không có turn_mentioned)" if not tr[k]["determinable_turns"]
                   else {t: len(tr[k][t]) for t in ("TA1", "TA1_opening")}) for k in rows}
    C["4_new_write_and_target"] = {"writes_new": w_new, "writes_all": wn, "wrong_target_new": t_new, "wrong_target_all": tn,
                                   "ta1_ref": ta1_ref,
                                   "rule": "TA1 / TA1_opening tính TUYỆT ĐỐI (có là lỗi cứng, không so mốc); H_B / ghi sai tính MỚI so mốc"}
    if any(x["type"] in HARD_WRITE for v in w_new.values() for x in v) or any(t_new[k]["H_B"] for k in rows) \
            or any(tn[k]["TA1"] or tn[k]["TA1_opening"] for k in rows):
        hard.append("4_new_write_and_target")
    if any(x["type"] in HARD_WRITE for v in wn.values() for x in v):
        investigate.append("4_known_writes")          # ghi sai đã có ở mốc: không miễn, giữ trong báo cáo quyết định
    if any(x["type"] == "unexpected" for v in w_new.values() for x in v) or any(t_new[k]["H_A_suspect"] for k in rows):
        investigate.append("4_new_write_and_target")

    # 5. chỉ số BTC + ngưỡng điều tra + phân loại MỌI ca mới trượt
    M, R = {}, {}
    for k in rows:
        M[k] = btc_metrics(B, scen, _trace(rows[k]))
        R[k] = btc_metrics(B, scen, _trace(ref_rows[k]))
    cls = {}
    for k in rows:
        newf = {kk: v for kk, v in M[k]["failures"].items() if kk not in R[k]["failures"]}
        bad_calls_w = {(x["scenario"], x["call"]) for x in wn[k]}
        unsup = {tuple(x["where"].split("/")[:2]) for x in uc[k] if x["hard"]}
        tgt = {tuple(x["where"].split("/")[:2]) for t in TL for x in tn[k][t]}
        out = []
        for (s, c), reasons in sorted(newf.items()):
            cat = []
            if (s, c) in bad_calls_w or (s, c) in unsup:
                cat.append("wrong_write")
            if (s, c) in tgt:
                cat.append("wrong_target")
            out.append({"call": f"{s}/{c}", "category": cat or ["khác"], "btc_reasons": reasons})
        cls[k] = out
    if any("wrong_write" in x["category"] or "wrong_target" in x["category"] for v in cls.values() for x in v):
        hard.append("5_new_failures")
    if any(x["category"] == ["khác"] for v in cls.values() for x in v):
        investigate.append("5_new_failures")
    C["5_new_failures_classified"] = cls

    th = {}
    for k in rows:
        tsr_ok = M[k]["tsr_passed"] >= R[k]["tsr_passed"] - TSR_SLACK_CASES
        hn, hr = M[k]["hr_price"]["exact"], R[k]["hr_price"]["exact"]
        hr_ok = hn is not None and hr is not None and hn <= hr + HR_SLACK_PT + 1e-9
        th[k] = {"tsr_new_ref": (M[k]["tsr_passed"], R[k]["tsr_passed"], M[k]["tsr_total"]), "tsr_within": tsr_ok,
                 "hr_price_new": {x: M[k]["hr_price"][x] for x in ("value", "wrong", "total")},
                 "hr_price_ref": {x: R[k]["hr_price"][x] for x in ("value", "wrong", "total")}, "hr_within": hr_ok}
        if not (tsr_ok and hr_ok):
            investigate.append(f"6_thresholds:{k}")
    C["6_investigation_thresholds"] = th

    # 7. RQR: tỷ lệ + tử / mẫu; câu hỏi thừa MỚI kiểm riêng
    rq = {}
    for k in rows:
        n_, r_ = M[k]["rqr"], R[k]["rqr"]
        newq = new_items(n_["items"], r_["items"], lambda x: (x["scenario"], x["call"], x["slot"], x["type"]))
        within = n_["exact"] is not None and r_["exact"] is not None and n_["exact"] <= r_["exact"] + RQR_SLACK_PT + 1e-9
        rq[k] = {"new": {x: n_[x] for x in ("value", "redundant", "total_questions")},
                 "ref": {x: r_[x] for x in ("value", "redundant", "total_questions")},
                 "within_slack": within, "new_redundant_questions": newq}
        if not within or newq:
            investigate.append(f"7_rqr:{k}")
    C["7_rqr"] = rq

    # 8. an toàn ghi + vận hành
    forb = {k: [x for x in wn[k] if x["type"] == "forbidden"] for k in rows}
    api = {}
    for k in rows:
        cnt = D.api_errors(rows[k])["counts"]
        api[k] = {x: cnt[x] for x in API_KEYS if cnt.get(x)}
    C["8_ops"] = {"forbidden_writes": forb, "api_errors": api}
    if any(forb.values()) or any(api.values()):
        hard.append("8_ops")
    if latency is None:
        C["8_ops"]["latency"] = "THIẾU"
        incomplete.append("8_ops:latency")
    else:
        lc = latency["configs"]
        audit = {k: (lc.get(k) or {}).get("audit_status") for k in rows}
        emit_bad = {k: (lc.get(k) or {}).get("emit_check_failed") for k in rows}
        ttft = ((lc.get("full") or {}).get("ttft") or {}).get("p95_ms")
        C["8_ops"].update({"audit_status": audit, "emit_check_failed": emit_bad, "ttft_p95_full": ttft, "ttft_p95_max": TTFT_P95_MAX})
        if any(not a or set(a) - {"ok", "partial"} for a in audit.values()) or any(emit_bad.values()) \
                or ttft is None or ttft > TTFT_P95_MAX:
            hard.append("8_ops:latency")

    # 10. địa chỉ ghi vào đơn (v5, phương án C): đuôi thừa / sai so với địa chỉ của kịch bản. MỚI so mốc → lỗi cứng;
    # có ở cả mốc → ĐIỀU TRA và giữ trong danh sách lỗi đã biết (không miễn).
    ak = lambda x: (x["where"], x["type"])
    aa = {k: D.address_audit(scen, rows[k]) for k in rows}
    an = {k: [x for x in aa[k]["examples"] if x["type"] in ADDRESS_BAD] for k in rows}
    ar = {k: [x for x in D.address_audit(scen, ref_rows[k])["examples"] if x["type"] in ADDRESS_BAD] for k in rows}
    a_new = {k: new_items(an[k], ar[k], ak) for k in rows}
    C["10_address"] = {"counts": {k: aa[k]["counts"] for k in rows}, "bad_all": an, "bad_new": a_new}
    if any(a_new.values()):
        hard.append("10_address")
    elif any(an.values()):
        investigate.append("10_address:known")

    C["9_info"] = {"metrics_new": {k: {"tsr": f"{M[k]['tsr_passed']}/{M[k]['tsr_total']}", "hr_price": M[k]["hr_price"]["value"],
                                       "rqr": M[k]["rqr"]["value"]} for k in rows},
                   "metrics_ref": {k: {"tsr": f"{R[k]['tsr_passed']}/{R[k]['tsr_total']}", "hr_price": R[k]["hr_price"]["value"],
                                       "rqr": R[k]["rqr"]["value"]} for k in rows}}
    verdict = "KHÔNG ĐẠT" if hard else "CHƯA ĐỦ" if incomplete else "CẦN ĐIỀU TRA" if investigate else "ĐẠT"
    return verdict, {"hard": hard, "incomplete": incomplete, "investigate": investigate}, C


def _trace(rows):
    d = collections.defaultdict(list)
    for r in rows:
        d[(r["scenario_id"], r["call"])].append(r)
    for k in d:
        d[k].sort(key=lambda r: r["turn"])
    return d


def load_rows(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load_checks(specs):
    out = {}
    for x in specs:
        name, path = x.split("=", 1)
        d = out.setdefault(name, {})
        for c in json.load(open(path, encoding="utf-8")):
            d[c["check"]] = max(d.get(c["check"], 0), int(c["rc"] != 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    for x in ("--scenarios", "--full", "--baseline", "--ref-full", "--ref-baseline", "--out"):
        ap.add_argument(x, required=True)
    ap.add_argument("--expect-n", type=int, default=92)
    ap.add_argument("--latency")
    ap.add_argument("--checks", action="append", default=[])
    ap.add_argument("--label", default="v38 dev 92")
    a = ap.parse_args()
    B = _btc_cached()
    scen = B.load_scenarios(a.scenarios)
    rows = {"full": load_rows(a.full), "baseline": load_rows(a.baseline)}
    ref = {"full": load_rows(a.ref_full), "baseline": load_rows(a.ref_baseline)}
    raw_ids = {k: {r["scenario_id"] for r in v} for k, v in rows.items()}
    rows = {k: [r for r in v if r["scenario_id"] in scen] for k, v in rows.items()}       # mọi tiêu chí tính trên đúng bộ kịch bản
    ref = {k: [r for r in v if r["scenario_id"] in scen] for k, v in ref.items()}
    lat = json.load(open(a.latency, encoding="utf-8")) if a.latency and os.path.exists(a.latency) else None
    verdict, why, C = evaluate(scen, rows, ref, lat, load_checks(a.checks), a.expect_n, raw_ids)
    out = {"criteria_version": CRITERIA_VERSION, "label": a.label, "verdict": verdict, "why": why,
           "note": "ĐẠT chỉ là đủ điều kiện ĐỀ XUẤT đóng b2-final; người dùng quyết. Ngưỡng TSR / HR / RQR là ngưỡng điều tra.",
           "criteria": C}
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "dev_v38_gate.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = [f"# Cổng {a.label} ({CRITERIA_VERSION}): {verdict}", "", f"- lỗi cứng: {why['hard']}", f"- thiếu: {why['incomplete']}",
         f"- cần điều tra: {why['investigate']}", ""]
    for k, v in C.items():
        L.append(f"- {k}: " + json.dumps(v, ensure_ascii=False)[:1500])
    open(os.path.join(a.out, "dev_v38_gate.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:6]))
    raise SystemExit({"KHÔNG ĐẠT": 3, "CHƯA ĐỦ": 4, "CẦN ĐIỀU TRA": 5, "ĐẠT": 0}[verdict])


if __name__ == "__main__":
    main()
