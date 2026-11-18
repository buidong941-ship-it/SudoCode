"""Probe 07/11: LLM bỏ phiếu chọn hàm (planner kiểu "LLM chọn hành động, code thực thi"), so với planner luật.

    python scripts/function_probe.py --backend qwen --out runs/function_probe     # cần vLLM (serve_llm.sh start)
    python scripts/function_probe.py --backend none --out runs/function_probe     # chỉ chấm mốc luật, không gọi model

Đầu vào: datagen/function_probe/functions.json (danh sách hàm) + items.jsonl (dựng bằng datagen/function_probe/build_items.py).
Mỗi mục: lời khách + câu nhân viên ngay trước + trạng thái (đã có đơn chưa, sản phẩm đã nhắc). Code lọc hàm theo
`available_if`, LLM chọn 1–3 hàm (hàm chính trước), JSON schema enum, nhiệt độ 0, không cache.
Không nối vào agent, không đổi hành vi agent.

Chỉ số (mỗi phần A/B/C chấm riêng; C là lượt của 26 cuộc gọi trượt holdout v3 — chỉ để đánh giá):
  primary   hàm chính của nhãn có trong dự đoán
  top1      hàm đầu tiên dự đoán thuộc gold ∪ accept (mốc luật không có thứ tự → không tính)
  exact     gold ⊆ dự đoán ⊆ gold ∪ accept
  action    như exact nhưng chỉ xét hàm state_change (tạo / sửa đơn, giỏ, hẹn gọi lại) — quyết định TSR
"""
import argparse, json, os, re, sys, time
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
D = os.path.join(ROOT, "datagen", "function_probe")


def candidates(funcs, state):
    return [n for n, f in funcs.items() if not f.get("available_if") or state.get(f["available_if"])]


def fold(s):
    import unicodedata
    s = (s or "").lower().replace("đ", "d")
    return re.sub(r"\s+", " ", "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")).strip()


CLOSE_CUE = re.compile(r"\b(len don|chot|dat (luon|hang|don)|lay (du|het|ca|luon)|giao (ve|toi|cho|qua)|ship (ve|toi)|gui ve)\b")
QUESTION = re.compile(r"(\?|\b(duoc khong|khong em|may ngay|bao lau|co mat|co ton|phai khong|dung khong)\b)")


def apply_rules(pred, item, funcs):
    """Luật cứng (functions_v2.json) áp SAU khi LLM chọn: implies_if, conflicts."""
    p, st, f = list(pred), item.get("state") or {}, fold(item["text"])
    for n in list(p):
        imp = (funcs.get(n) or {}).get("implies_if") or {}
        if imp.get("no_order") and not st.get("has_order") and imp["no_order"] not in p:
            p.append(imp["no_order"])
    for n in list(p):
        for other, how in ((funcs.get(n) or {}).get("conflicts") or {}).items():
            if n in p and other in p:
                if how == "keep_place_order_if_close_cue":
                    p.remove(n if CLOSE_CUE.search(f) else other)
                elif how == "keep_policy_if_question":
                    p.remove(n if QUESTION.search(f) else other)
    return p


def prompt(item, funcs, cands, rules=()):
    st = item.get("state") or {}
    lines = [f"- {n}: {funcs[n]['description']}" for n in cands]
    return ("Bạn là bộ điều phối của nhân viên bán hàng qua điện thoại/chat của một shop. Đọc câu khách vừa nói và chọn "
            "các HÀM mà hệ thống cần chạy ở lượt này. Chọn từ 1 đến 3 hàm, hàm quan trọng nhất đứng đầu. Chỉ chọn hàm "
            "có trong danh sách; không chọn hàm chỉ vì câu nhắc tới một từ khoá.\n\n"
            "Danh sách hàm:\n" + "\n".join(lines) + "\n\n"
            + ("Quy tắc chọn:\n" + "\n".join(f"- {r}" for r in rules) + "\n\n" if rules else "")
            + f"Trạng thái: khách {'ĐÃ có' if st.get('has_order') else 'CHƯA có'} đơn hàng đã đặt với shop. "
            f"Sản phẩm đã nhắc trong cuộc gọi: {', '.join(st.get('discussed') or []) or '(chưa có)'}.\n"
            f"Câu nhân viên vừa nói: {item.get('agent_prev') or '(đầu cuộc gọi)'}\n"
            f"Câu khách: {item['text']}\n\n"
            "Trả JSON {\"functions\": [tên hàm, ...]}.")


def ask_qwen(item, funcs, cands, rules=()):
    from core.llm.deepseek import LLM
    schema = {"type": "object", "required": ["functions"], "additionalProperties": False,
              "properties": {"functions": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string", "enum": cands}}}}
    d = LLM("qwen", role="planner").json(prompt(item, funcs, cands, rules), schema=schema, max_tokens=80, cache=False)
    out = []
    for f in (d.get("functions") or []):
        if f in cands and f not in out:
            out.append(f)
    return out


def score(pred, item, sc_set, ordered=True):
    G, A, P = set(item["gold"]), set(item.get("accept") or []), list(pred or [])
    Ps = set(P)
    r = {"primary": item["primary"] in Ps,
         "exact": G <= Ps and Ps <= G | A,
         "action": (G & sc_set) <= (Ps & sc_set) and (Ps & sc_set) <= ((G | A) & sc_set)}
    if ordered:
        r["top1"] = bool(P) and P[0] in G | A
    return r


def summarize(rows, key, sc_set):
    out = {}
    for part in ("A", "B", "C", "D"):
        xs = [r for r in rows if r["part"] == part and r.get(key) is not None]
        if not xs:
            continue
        s = defaultdict(int)
        for r in xs:
            for k, v in r[key + "_score"].items():
                s[k] += int(v)
        out[part] = {"n": len(xs), **{k: round(100 * v / len(xs), 1) for k, v in s.items()}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["qwen", "none"], default="qwen")
    ap.add_argument("--out", default="runs/function_probe")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--functions", default="functions.json", help="file trong datagen/function_probe/")
    ap.add_argument("--rules-pure", default=None, help="rules_pure.json từ scripts/function_probe_rules.py")
    ap.add_argument("--shard", default=None, help="k/n: chỉ chạy items[k::n] (chia job ra nhiều máy, gộp lại sau)")
    a = ap.parse_args()
    spec = json.load(open(os.path.join(D, a.functions), encoding="utf-8"))
    funcs, prules = spec["functions"], spec.get("prompt_rules") or []
    pure = json.load(open(a.rules_pure, encoding="utf-8")) if a.rules_pure and os.path.exists(a.rules_pure) else {}
    sc_set = {n for n, f in funcs.items() if f.get("state_change")}
    items = [json.loads(l) for l in open(os.path.join(D, "items.jsonl"), encoding="utf-8")]
    if a.shard:
        k, n = (int(x) for x in a.shard.split("/"))
        items = items[k::n]
    if a.limit:
        items = items[:a.limit]
    os.makedirs(a.out, exist_ok=True)
    rows, ms, errs = [], [], 0
    for i, it in enumerate(items):
        cands = candidates(funcs, it.get("state") or {})
        row = {k: it.get(k) for k in ("id", "part", "group", "text", "gold", "accept", "primary", "rules")}
        row["candidates"] = len(cands)
        if it.get("rules") is not None:
            row["rules_score"] = score(it["rules"], it, sc_set, ordered=False)
        pr = pure.get(it["id"]) or {}
        if pr.get("found") and pr.get("setup_ok", True):
            row["rules_pure"] = pr["functions"]
            row["rules_pure_score"] = score(pr["functions"], it, sc_set, ordered=False)
        if a.backend == "qwen":
            t0 = time.perf_counter()
            try:
                row["qwen_raw"] = ask_qwen(it, funcs, cands, prules)
                row["qwen"] = apply_rules(row["qwen_raw"], it, funcs)
            except Exception as e:
                row["qwen_raw"], row["qwen"], row["error"] = [], [], f"{type(e).__name__}: {str(e)[:160]}"
                errs += 1
            ms.append(int((time.perf_counter() - t0) * 1000))
            row["qwen_raw_score"] = score(row["qwen_raw"], it, sc_set)
            row["qwen_score"] = score(row["qwen"], it, sc_set)
        rows.append(row)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(items)}", flush=True)
    summ = {"n_items": len(rows), "errors": errs, "functions_file": a.functions,
            "rules_trace": summarize(rows, "rules", sc_set), "rules_pure": summarize(rows, "rules_pure", sc_set)}
    if a.backend == "qwen":
        ms.sort()
        summ["qwen_raw"] = summarize(rows, "qwen_raw", sc_set)
        summ["qwen_rules"] = summarize(rows, "qwen", sc_set)
        summ["qwen_ms"] = {"p50": ms[len(ms) // 2], "p95": ms[int(len(ms) * 0.95) - 1]} if ms else None
        recall, total = Counter(), Counter()
        for r in rows:
            for f in r["gold"]:
                total[f] += 1
                recall[f] += f in r["qwen"]
        summ["qwen_recall_by_function"] = {f: f"{recall[f]}/{total[f]}" for f in sorted(total)}
    json.dump({"summary": summ, "rows": rows}, open(os.path.join(a.out, "function_probe.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    if a.backend == "qwen":
        print("\n# Sai (Qwen, exact=False)")
        for r in rows:
            if not r["qwen_score"]["exact"]:
                print(f"{r['part']} {r['id']}: gold={r['gold']} qwen={r['qwen']} raw={r['qwen_raw']} pure={r.get('rules_pure')} | {r['text'][:90]}")


if __name__ == "__main__":
    main()
