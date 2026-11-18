#!/usr/bin/env python3
"""Đối chiếu ảnh hưởng history / state giữa hai lần chạy (14/11, §8.11): mốc vòng F (v36) và F1b (v37) trên bộ 19.

Mỗi lượt so ĐẦU VÀO của bộ hiểu DeepSeek mà trace / memory.db ghi được:
  câu khách, hội thoại gần đây (6 dòng cuối trong cuộc gọi), tóm tắt phiên trước (memory.db sessions), slot vừa hỏi
  (question_slot lượt trước), request_state (hold / proposal / items — đại diện cho state_ctx, không ghi nguyên văn);
và ĐẦU RA: hiểu (intent / asks / request_items / response), bước planner, goals, câu trả lời.
Phân loại lượt lệch ĐẦU TIÊN của mỗi kịch bản:
  same_input_understanding_differs → biến động DeepSeek;  same_understanding_steps_differ → biến động Jev;
  same_steps_text_differs → render đổi (F1b nếu lượt có câu F1b) hoặc Qwen;  input_differs → lệch từ phía trên (đã ghi nguồn).
Chỉ đọc file; không gọi model.
    python scripts/f1b_divergence.py --ref-full A --ref-base B --new-full C --new-base D --ref-db X.db --new-db Y.db --out <dir>"""
import argparse
import json
import os
import re
import sqlite3

F1B_TXT = re.compile(r"không có quà tặng kèm|chưa đủ điều kiện áp dụng chương trình khuyến mãi nào|khuyến mãi hiện có không áp dụng"
                     r"|đã hết hạn rồi ạ")


def load(p, ids=None):
    out = {}
    for ln in open(p, encoding="utf-8"):
        if ln.strip():
            r = json.loads(ln)
            if ids is None or r["scenario_id"] in ids:
                out[(r["scenario_id"], r["call"], r["turn"])] = r
    return out


def summaries(db):
    if not db or not os.path.isfile(db):
        return {}
    c = sqlite3.connect(db)
    return {sid: (summ, outcome) for sid, summ, outcome in c.execute("select session_id, summary, outcome from sessions")}


def und(r):
    u = r.get("understanding") or {}
    return {"intent": u.get("intent"), "asks": sorted(u.get("asks") or []),
            "items": sorted((i.get("kind"), i.get("target_ref")) for i in u.get("request_items") or []), "response": u.get("response")}


def steps(r):
    return [(s.get("action"), s.get("target_ref")) for s in ((r.get("planner") or {}).get("loop") or {}).get("steps") or []]


def rs(r):
    x = r.get("request_state") or {}
    return json.dumps({k: x.get(k) for k in ("hold", "proposal", "items", "blocked")}, ensure_ascii=False, sort_keys=True)


def inputs(rows, k, summ):
    sid, call, t = k
    prev = [rows[(sid, call, i)] for i in range(1, t) if (sid, call, i) in rows]
    hist = []
    for p in prev:
        hist += [p.get("customer_text"), p.get("agent_text")]
    pc = int(call.split("_")[1]) - 1
    return {"text": rows[k].get("customer_text"), "recent": hist[-6:],
            "summary": (summ.get(f"{sid}:call_{pc}") or (None,))[0] if pc >= 1 else None,
            "asked": prev[-1].get("question_slot") if prev else None, "state": rs(prev[-1]) if prev else None}


def compare(ref, new, sref, snew, cfg):
    out = {}
    for sid in sorted({k[0] for k in new}):
        keys = sorted(k for k in new if k[0] == sid)
        turns, first = [], None
        for k in keys:
            if k not in ref:
                turns.append({"turn": f"{k[1]}/t{k[2]}", "class": "missing_in_ref"})
                continue
            a, b = ref[k], new[k]
            ia, ib = inputs(ref, k, sref), inputs(new, k, snew)
            diff_in = [x for x in ia if ia[x] != ib[x]]
            cls = None
            if diff_in:
                cls = "input_differs"
            elif und(a) != und(b):
                cls = "same_input_understanding_differs"
            elif steps(a) != steps(b):
                cls = "same_understanding_steps_differ"
            elif (a.get("agent_text") or "") != (b.get("agent_text") or ""):
                cls = "same_steps_text_differs" + ("(F1b)" if F1B_TXT.search(b.get("agent_text") or "") else "(other)")
            rec = {"turn": f"{k[1]}/t{k[2]}", "class": cls or "same"}
            if cls:
                rec.update(input_fields=diff_in, und_ref=und(a), und_new=und(b), steps_ref=steps(a), steps_new=steps(b),
                           text_ref=(a.get("agent_text") or "")[:160], text_new=(b.get("agent_text") or "")[:160])
                if "summary" in diff_in:
                    rec.update(summary_ref=ia["summary"], summary_new=ib["summary"])
                if first is None:
                    first = rec
            turns.append(rec)
        out[sid] = {"first_divergence": first, "turns": turns}
    return out


def main():
    ap = argparse.ArgumentParser()
    for x in ("--ref-full", "--ref-base", "--new-full", "--new-base", "--out"):
        ap.add_argument(x, required=True)
    ap.add_argument("--ref-db")
    ap.add_argument("--new-db")
    ap.add_argument("--ref-db-base")
    ap.add_argument("--new-db-base")
    a = ap.parse_args()
    newf, newb = load(a.new_full), load(a.new_base)
    ids = {k[0] for k in newf} | {k[0] for k in newb}
    res = {"full": compare(load(a.ref_full, ids), newf, summaries(a.ref_db), summaries(a.new_db), "full"),
           "baseline": compare(load(a.ref_base, ids), newb, summaries(a.ref_db_base), summaries(a.new_db_base), "baseline")}
    os.makedirs(a.out, exist_ok=True)
    json.dump(res, open(os.path.join(a.out, "divergence.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    L = ["# Đối chiếu history / state: mốc vòng F (v36) và F1b (v37), bộ 19", "",
         "| config | kịch bản | lượt lệch đầu tiên | loại | trường đầu vào khác |", "|---|---|---|---|---|"]
    for cfg, d in res.items():
        for sid, v in d.items():
            f = v["first_divergence"]
            L.append(f"| {cfg} | {sid} | {f['turn'] if f else '-'} | {f['class'] if f else 'giống hệt'} | "
                     f"{', '.join(f.get('input_fields') or []) if f else ''} |")
    open(os.path.join(a.out, "divergence.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
