#!/usr/bin/env python3
"""Danh mục dataset tập trung (13/11/2026) — đọc datagen/datasets/registry.json, không sửa hay di chuyển file gốc.

    python scripts/dataset_registry.py index                       # → datagen/datasets/registry.lock.json + index.jsonl
    python scripts/dataset_registry.py suites                      # giải suites/*.json → suites/resolved/<suite>.json
    python scripts/dataset_registry.py materialize --suite regression --out /tmp/suites/regression
    python scripts/dataset_registry.py audit --release h13@r1 --out <dir>   # chống trùng 3 lớp + coverage + canary

`materialize` chép đúng các file của suite (đã giải) vào một thư mục staging để `run_eval.py --scenarios <dir>` hoặc
`run_suite.py --sets <dir>` đọc được; kiểm sha256 với index và báo trùng scenario_id. Runner hiện CHƯA đọc suite
manifest trực tiếp. Suite `guarded` (holdout mới) chỉ materialize khi có `--allow-guarded` (người dùng đã duyệt đo).

Chỉ dùng thư viện chuẩn + eval/reference_eval.py của BTC (cho canary). Không gọi model.
"""
import argparse
import collections
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "datagen", "datasets")
REG = os.path.join(DS, "registry.json")
LOCK = os.path.join(DS, "registry.lock.json")
INDEX = os.path.join(DS, "index.jsonl")
SUITES = os.path.join(DS, "suites")
RESOLVED = os.path.join(SUITES, "resolved")
SCENARIO_FORMATS = ("btc_scenario", "probe_scenario")


# --------------------------------------------------------------------------- tiện ích
def sha_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def fold(text):
    s = (text or "").replace("đ", "d").replace("Đ", "D").lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", s)).strip()


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def key_of(ds, part=None):
    return f"{ds['dataset_id']}@{ds['version']}" + (f"/{part['part']}" if part else "")


def load_registry():
    return json.load(open(REG, encoding="utf-8"))


def part_format(ds, part):
    return part.get("format") or ds.get("format")


def scenario_files(path):
    """Cùng quy tắc với harness/loader.py: bỏ file bắt đầu '_' / 'manifest', report."""
    if os.path.isfile(path):
        return [path]
    out = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        b = os.path.basename(f)
        if b.startswith(("_", "manifest")) or b in ("validate_report.json", "report.json"):
            continue
        out.append(f)
    return out


def customer_turns(sc):
    for name in sorted(sc.get("calls", {}), key=lambda c: int(c.split("_")[1]) if c.split("_")[-1].isdigit() else 99):
        for t in sc["calls"][name].get("customer_turns") or []:
            yield t


def skeleton(sc):
    """Khung diễn biến, bỏ SKU/ngày/tên/lời: mỗi call → kênh, dạng input, tool chấm, action, cờ âm, outcome."""
    out = []
    for name in sorted(sc.get("calls", {}), key=lambda c: int(c.split("_")[1]) if c.split("_")[-1].isdigit() else 99):
        c = sc["calls"][name]
        si = c.get("success_if") or {}
        am = si.get("args_match") or {}
        neg = "neg" if (si and si.get("tool_called") is None and (si.get("must_not_call_tools") or si.get("agent_must_say") is not None)) else ""
        flags = "".join(f for f, on in (("S", si.get("must_say_any")), ("A", "agent_must_say" in si), ("F", si.get("forbidden_claims")),
                                          ("R", si.get("trace_must_not_match")), ("T", si.get("total_match_vnd") is not None),
                                          ("Q", am.get("qty") not in (None, 1))) if on)
        out.append("|".join([c.get("channel", "hotline"), c.get("input_mode", "text"), str(si.get("tool_called") if si else "-"),
                             str(am.get("action", "")), neg, flags, str(c.get("expected_outcome", ""))]))
    return " > ".join(out)


def scenario_info(path):
    sc = json.load(open(path, encoding="utf-8"))
    if not (isinstance(sc, dict) and "calls" in sc and "scenario_id" in sc):
        return None
    meta = sc.get("_meta") or {}
    turns = list(customer_turns(sc))
    return {"scenario_id": sc["scenario_id"], "file": rel(path), "sha256": sha_file(path),
            "template_id": meta.get("template_id"), "family": meta.get("template_family") or meta.get("template_id"),
            "polarity": meta.get("polarity"), "group": meta.get("group"),
            "hard_case": sc.get("hard_case"), "n_calls": len(sc.get("calls", {})), "n_turns": len(turns),
            "channels": [c.get("channel", "hotline") for c in sc.get("calls", {}).values()],
            "input_modes": [c.get("input_mode", "text") for c in sc.get("calls", {}).values()],
            "phone_sha": hashlib.sha256(str(sc.get("customer_phone", "")).encode()).hexdigest()[:12],
            "customer_id": meta.get("customer_id"), "synthetic_customer": meta.get("synthetic_customer"),
            "text_sha": hashlib.sha256(" | ".join(fold(t) for t in turns).encode()).hexdigest()[:16],
            "skeleton": skeleton(sc)}


def aggregate_sha(files):
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(rel(f).encode())
        h.update(bytes.fromhex(sha_file(f)))
    return h.hexdigest()


# --------------------------------------------------------------------------- index
def cmd_index(a):
    reg = load_registry()
    rows, parts_out = [], []
    for ds in reg["datasets"]:
        for part in ds["parts"] + [{"part": "raw:" + p.split("/")[-1], "path": p, "role": "raw_source", "_raw": True}
                                   for p in ds.get("raw_paths", [])]:
            path = os.path.join(ROOT, part["path"])
            fmt = part_format(ds, part)
            entry = {"key": key_of(ds, part), "path": part["path"], "format": fmt, "role": part.get("role"),
                     "lineage_group": ds.get("lineage_group"), "canonical": ds.get("canonical"), "raw": bool(part.get("_raw"))}
            if not os.path.exists(path):
                entry["missing"] = True
                parts_out.append(entry)
                continue
            if fmt in SCENARIO_FORMATS:
                files = scenario_files(path)
                infos = [i for i in (scenario_info(f) for f in files) if i]
                entry.update({"n_files": len(files), "n_scenarios": len(infos), "sha256": aggregate_sha(files),
                              "n_templates": len({i["template_id"] for i in infos if i["template_id"]}),
                              "n_families": len({i["family"] for i in infos if i["family"]}),
                              "n_hard_case_types": len({i["hard_case"] for i in infos if i["hard_case"]}),
                              "n_calls": sum(i["n_calls"] for i in infos), "n_turns": sum(i["n_turns"] for i in infos)})
                if not part.get("_raw"):
                    for i in infos:
                        rows.append({"dataset_id": ds["dataset_id"], "version": ds["version"], "part": part["part"],
                                     "lineage_group": ds.get("lineage_group"), "role": part.get("role"), **i})
            elif os.path.isdir(path):
                files = [f for f in glob.glob(os.path.join(path, "**", "*"), recursive=True) if os.path.isfile(f)]
                entry.update({"n_files": len(files), "sha256": aggregate_sha(files)})
            elif fmt == "json":
                data = json.load(open(path, encoding="utf-8"))
                n = len(data) if isinstance(data, list) else max((len(v) for v in data.values() if isinstance(v, list)), default=None)
                entry.update({"n_files": 1, "n_records": n, "sha256": sha_file(path)})
            else:
                n = sum(1 for ln in open(path, encoding="utf-8") if ln.strip())
                entry.update({"n_files": 1, "n_records": n - (1 if fmt == "tsv" else 0), "sha256": sha_file(path)})
            parts_out.append(entry)
    # tổng: file vs kịch bản độc lập (không cộng raw/final, bản vá, paraphrase: gom theo lineage_group + scenario_id)
    scen_parts = [p for p in parts_out if p.get("format") in SCENARIO_FORMATS and not p.get("missing")]
    independent = collections.defaultdict(set)
    for r in rows:
        if r["role"] != "component_check":
            independent[r["lineage_group"]].add(r["scenario_id"])
    summary = {"scenario_files_all_parts_incl_raw": sum(p.get("n_files", 0) for p in scen_parts),
               "scenario_files_run_parts": sum(p.get("n_files", 0) for p in scen_parts if not p["raw"]),
               "independent_scenarios_by_lineage": {g: len(v) for g, v in sorted(independent.items())},
               "independent_scenarios_total": sum(len(v) for v in independent.values()),
               "independent_scenarios_team_only": sum(len(v) for g, v in independent.items() if g != "btc_sample"),
               "note": "Độc lập = scenario_id khác nhau trong cùng lineage_group (raw/final, bản vá, paraphrase cùng lineage chỉ tính 1). "
                       "function_probe (component_check) không tính."}
    lock = {"generated_by": "scripts/dataset_registry.py index", "registry_sha256": sha_file(REG), "parts": parts_out, "summary": summary}
    out_lock = a.lock or LOCK
    out_index = a.index or INDEX
    json.dump(lock, open(out_lock, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(out_index, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    missing = [p["key"] for p in parts_out if p.get("missing")]
    if missing:
        print("[warn] không thấy (bình thường nếu là dataset/ trên Kaggle):", missing)
    print(f"index: {len(rows)} dòng → {rel(out_index)}; lock → {rel(out_lock)}")


def load_index():
    if not os.path.exists(INDEX):
        sys.exit("chưa có index.jsonl — chạy `index` trước")
    return [json.loads(ln) for ln in open(INDEX, encoding="utf-8") if ln.strip()]


# --------------------------------------------------------------------------- suites
def _select(rows, sel):
    rows = sorted(rows, key=lambda r: r["scenario_id"])
    if sel.get("hard_only"):
        rows = [r for r in rows if r.get("hard_case")]
    if sel.get("normal_only"):
        rows = [r for r in rows if not r.get("hard_case")]
    if sel.get("all"):
        return rows
    per, n = sel.get("per"), int(sel.get("n", 1))
    if not per:
        return rows[:n]
    seen, out = collections.Counter(), []
    for r in rows:
        k = r.get(per) or "(none)"
        if seen[k] < n:
            out.append(r)
            seen[k] += 1
    return out


def resolve_suite(name, rows, cache):
    if name in cache:
        return cache[name]
    spec = json.load(open(os.path.join(SUITES, f"{name}.json"), encoding="utf-8"))
    if spec.get("materializable") is False:
        cache[name] = (spec, None)
        return cache[name]
    members, seen = [], set()
    for m in spec["members"]:
        if m.get("from_suite"):
            pool = resolve_suite(m["from_suite"], rows, cache)[1]
            pool = [r for r in pool if r["dataset_id"] == m["dataset"] and r["version"] == m["version"]]
        else:
            pool = [r for r in rows if r["dataset_id"] == m["dataset"] and r["version"] == m["version"] and r["part"] == m["part"]]
            if not pool:
                sys.exit(f"suite {name}: không có kịch bản cho {m}")
        for r in _select(pool, m.get("select", {"all": True})):
            k = (r["dataset_id"], r["version"], r["scenario_id"])
            if k not in seen:
                seen.add(k)
                members.append(r)
    cache[name] = (spec, members)
    return cache[name]


def cmd_suites(a):
    rows = load_index()
    os.makedirs(RESOLVED, exist_ok=True)
    cache = {}
    for f in sorted(glob.glob(os.path.join(SUITES, "*.json"))):
        name = os.path.basename(f)[:-5]
        spec, members = resolve_suite(name, rows, cache)
        if members is None:
            print(f"{name:<16} (không materialize: bộ kiểm thành phần)")
            continue
        ids = collections.Counter(r["scenario_id"] for r in members)
        dup = [k for k, v in ids.items() if v > 1]
        out = {"suite": name, "guarded": spec.get("guarded", False), "subset_of": spec.get("subset_of"), "n": len(members),
               "scenario_id_collisions": dup,
               "by_dataset": dict(collections.Counter(f"{r['dataset_id']}@{r['version']}/{r['part']}" for r in members)),
               "members": [{k: r[k] for k in ("dataset_id", "version", "part", "scenario_id", "file", "sha256", "template_id", "hard_case")}
                           for r in members]}
        if spec.get("subset_of"):
            parent = {(r["dataset_id"], r["version"], r["scenario_id"]) for r in resolve_suite(spec["subset_of"], rows, cache)[1]}
            out["outside_parent"] = [r["scenario_id"] for r in members if (r["dataset_id"], r["version"], r["scenario_id"]) not in parent]
        json.dump(out, open(os.path.join(RESOLVED, f"{name}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{name:<16} n={len(members):<4} {out['by_dataset']}" + (f"  TRÙNG ID: {dup}" if dup else ""))


# --------------------------------------------------------------------------- materialize
def cmd_materialize(a):
    path = os.path.join(RESOLVED, f"{a.suite}.json")
    if not os.path.exists(path):
        sys.exit(f"chưa giải suite {a.suite}: chạy `suites` trước")
    res = json.load(open(path, encoding="utf-8"))
    if res.get("guarded") and not a.allow_guarded:
        sys.exit(f"suite {a.suite} là holdout được bảo vệ: chỉ materialize khi người dùng đã duyệt đo (--allow-guarded) "
                 "và ghi exposure 'evaluated' vào registry.json")
    if res["scenario_id_collisions"]:
        sys.exit(f"suite {a.suite} trùng scenario_id {res['scenario_id_collisions']} — runner nạp theo scenario_id, không materialize")
    if os.path.exists(a.out) and os.listdir(a.out):
        sys.exit(f"{a.out} không rỗng; dùng thư mục mới để không trộn suite")
    os.makedirs(a.out, exist_ok=True)
    bad = []
    for m in res["members"]:
        src = os.path.join(ROOT, m["file"])
        if not os.path.exists(src) or sha_file(src) != m["sha256"]:
            bad.append(m["file"])
            continue
        shutil.copyfile(src, os.path.join(a.out, os.path.basename(src)))
    if bad:
        shutil.rmtree(a.out, ignore_errors=True)
        sys.exit(f"{len(bad)} file thiếu hoặc khác sha256 với index (dữ liệu đã đổi?): {bad[:5]}")
    json.dump({"suite": a.suite, "n": len(res["members"]), "source": rel(path),
               "members": [{k: m[k] for k in ("dataset_id", "version", "part", "scenario_id", "file", "sha256")} for m in res["members"]]},
              open(os.path.join(a.out, "_suite_manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"materialize {a.suite}: {len(res['members'])} kịch bản → {a.out}")


# --------------------------------------------------------------------------- audit
def _ngrams(text, n=8):
    tok = fold(text).split()
    return {tuple(tok[i:i + n]) for i in range(len(tok) - n + 1)}


def _load_eval():
    spec = importlib.util.spec_from_file_location("reference_eval", os.path.join(ROOT, "eval", "reference_eval.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mock():
    sys.path.insert(0, os.path.join(ROOT, "eval"))
    import mock_tools  # noqa: E402
    return mock_tools


def _row(sid, call, spec):
    return {"run_id": "canary", "config": "full", "scenario_id": sid, "call": call, "turn": 1,
            "customer_text": (spec.get("customer_turns") or [""])[0], "agent_text": "", "questions": [],
            "facts_used": list(spec.get("must_carry_over", [])), "claims": [], "tool_calls": [], "memory_writes": [],
            "latency": {"ttft_ms": 1, "total_ms": 1}}


def _perfect_call(sc, call, spec, mt, dates, wrong=False):
    """Trace 'đúng' theo success_if (như datagen/validate.smoke) hoặc 'sai có chủ ý' (wrong=True) để canary phải FAIL."""
    si = spec.get("success_if") or {}
    row = _row(sc["scenario_id"], call, spec)
    phone = sc["customer_phone"]
    addr = (sc.get("_meta") or {}).get("address")
    texts = []
    if si.get("must_say_any"):
        texts.append(si["must_say_any"][0])
    if "agent_must_say" in si:
        texts.append("em không có thông tin về vấn đề này")
    row["agent_text"] = " . ".join(texts) or "Dạ vâng ạ."
    row["claims"] = [{"field": k, "value": v} for k, v in (spec.get("ground_truth_facts") or {}).items()]
    tool, am = si.get("tool_called"), dict(si.get("args_match") or {})
    if tool == "handoff.transfer":
        row["tool_calls"].append({"name": tool, "args": {"brief": {k: "x" for k in set(mt.REQUIRED_BRIEF) | set(si.get("brief_must_contain", []))}}})
    elif tool == "order.create":
        items = si.get("also_ordered") or [am.get("sku")]
        for s in items:
            args = {**am} if s == am.get("sku") else {"sku": s, "price_vnd": mt.pricing_get_quote(
                s, on=dates[call], customer_phone=phone, address=addr, basket_skus=[x for x in items if x != s])["final_price_vnd"]}
            if "price_vnd" not in args:
                args["price_vnd"] = mt.pricing_get_quote(s, on=dates[call], customer_phone=phone, address=addr)["final_price_vnd"]
            args.setdefault("qty", 1)
            args.setdefault("customer_phone", phone)
            row["tool_calls"].append({"name": "order.create", "args": args, "result": {"order_id": "OD-canary", "status": "created"}})
    elif tool:
        am.setdefault("customer_phone", phone)
        row["tool_calls"].append({"name": tool, "args": am})
    if wrong:
        if tool == "order.create":
            row["tool_calls"][0]["args"]["price_vnd"] = int(row["tool_calls"][0]["args"].get("price_vnd") or 0) + 1000
        elif tool == "order.update":
            row["tool_calls"][0]["args"]["action"] = "return" if am.get("action") != "return" else "exchange_size"
        elif tool == "schedule.callback":
            row["tool_calls"][0]["args"]["callback_at"] = "2099-01-01T08:00"
        elif tool in ("order.status", "handoff.transfer"):
            row["tool_calls"] = []
        elif si.get("must_not_call_tools"):
            row["tool_calls"].append({"name": si["must_not_call_tools"][0], "args": {"customer_phone": phone}})
        else:
            row["agent_text"] = "Dạ vâng ạ."
    return row


def canary(scenarios, ev, mt):
    import datetime as _dt
    out = {"perfect_pass": 0, "empty_fail": 0, "wrong_fail": 0, "n": 0, "problems": []}
    for sc in scenarios:
        sid = sc["scenario_id"]
        names = sorted(sc["calls"], key=lambda c: int(c.split("_")[1]))
        dates, prev = {}, None
        for c in names:
            spec = sc["calls"][c]
            d = spec.get("call_date") or (_dt.date.fromisoformat(prev or mt.REF) + _dt.timedelta(days=int(spec.get("days_later", 0)))).isoformat()
            dates[c], prev = d, d
        graded = [c for c in names if sc["calls"][c].get("success_if")]
        if not graded:
            out["problems"].append({"scenario": sid, "problem": "không có success_if"})
            continue
        out["n"] += 1
        tr = {"perfect": collections.defaultdict(list), "empty": collections.defaultdict(list), "wrong": collections.defaultdict(list)}
        for c in names:
            spec = sc["calls"][c]
            tr["perfect"][(sid, c)].append(_perfect_call(sc, c, spec, mt, dates))
            tr["empty"][(sid, c)].append(_row(sid, c, spec))
            tr["wrong"][(sid, c)].append(_perfect_call(sc, c, spec, mt, dates, wrong=(c == graded[-1])))
        res = {k: ev.task_success_rate({sid: sc}, v) for k, v in tr.items()}
        ok_p = res["perfect"]["passed"] == res["perfect"]["total"]
        ok_e = res["empty"]["passed"] < res["empty"]["total"]
        ok_w = res["wrong"]["passed"] < res["wrong"]["total"]
        out["perfect_pass"] += ok_p
        out["empty_fail"] += ok_e
        out["wrong_fail"] += ok_w
        if not (ok_p and ok_e and ok_w):
            out["problems"].append({"scenario": sid, "perfect_pass": ok_p, "empty_fail": ok_e, "wrong_fail": ok_w,
                                    "reasons": [f["reasons"] for f in res["perfect"]["failures"]][:2]})
    return out


def cmd_audit(a):
    reg = load_registry()
    rows = load_index()
    ds_id, version = a.release.split("@")
    new = [r for r in rows if r["dataset_id"] == ds_id and r["version"] == version]
    old = [r for r in rows if not (r["dataset_id"] == ds_id and r["version"] == version)]
    if not new:
        sys.exit(f"không có kịch bản cho {a.release} trong index")
    text_unopened = set()
    for ds in reg["datasets"]:
        for p in ds["parts"]:
            if p.get("text_opened") is False:
                text_unopened.add(f"{ds['dataset_id']}@{ds['version']}/{p['part']}")
    rep = {"release": a.release, "n_scenarios": len(new)}

    # ---- lớp 1: hash file, văn bản chuẩn hóa của cả kịch bản, và từng lượt khách
    old_sha = {r["sha256"]: r for r in old}
    old_text = collections.defaultdict(list)
    for r in old:
        old_text[r["text_sha"]].append(f"{r['dataset_id']}@{r['version']}/{r['part']}:{r['scenario_id']}")
    turn_src = collections.defaultdict(set)
    new_turns = []
    for r in rows:
        sc = json.load(open(os.path.join(ROOT, r["file"]), encoding="utf-8"))
        tag = f"{r['dataset_id']}@{r['version']}/{r['part']}"
        for t in customer_turns(sc):
            if r in new:
                new_turns.append((r["scenario_id"], t))
            else:
                turn_src[fold(t)].add(tag)
    rep["layer1_exact"] = {
        "file_sha_dup_with_old": [r["scenario_id"] for r in new if r["sha256"] in old_sha],
        "scenario_text_dup_with_old": {r["scenario_id"]: old_text[r["text_sha"]] for r in new if r["text_sha"] in old_text},
        "new_turns": len(new_turns),
        "new_turns_identical_to_old_turn": sum(1 for _, t in new_turns if fold(t) in turn_src),
        "identical_turn_examples": [t for _, t in new_turns if fold(t) in turn_src][:15],
        "dup_within_release_text": [k for k, v in collections.Counter(r["text_sha"] for r in new).items() if v > 1],
    }
    # trùng/lineage trong toàn kho cũ (để báo canonical/duplicate khi kiểm kê)
    inv_dup = collections.defaultdict(set)
    for r in old:
        inv_dup[r["text_sha"]].add(f"{r['dataset_id']}@{r['version']}/{r['part']}")
    pair = collections.Counter()
    for s in inv_dup.values():
        s = sorted(s)
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                pair[f"{s[i]} == {s[j]}"] += 1
    rep["inventory_same_text_between_parts"] = dict(pair.most_common())

    # ---- lớp 2: lineage (khai báo trong registry) + SĐT/khách dùng lại + scenario_id trùng
    old_phone = collections.defaultdict(set)
    for r in old:
        old_phone[r["phone_sha"]].add(f"{r['dataset_id']}@{r['version']}")
    rep["layer2_lineage"] = {
        "declared": [{"key": f"{d['dataset_id']}@{d['version']}", "parent": d.get("parent_version"), "lineage": d.get("lineage"),
                      "supersedes": d.get("supersedes")} for d in reg["datasets"] if d.get("parent_version")],
        "scenario_id_collision_with_old": sorted({r["scenario_id"] for r in new} & {r["scenario_id"] for r in old}),
        "phone_reused_from_old": {r["scenario_id"]: sorted(old_phone[r["phone_sha"]]) for r in new if r["phone_sha"] in old_phone},
        # khách CRM (50 người của BTC) dùng chung giữa các bộ là không tránh được → chỉ báo; khách tổng hợp trùng SĐT mới chặn
        "synthetic_phone_reused_from_old": [r["scenario_id"] for r in new if r["phone_sha"] in old_phone and r.get("synthetic_customer")],
        "crm_customers_used": sorted({r["customer_id"] for r in new if r.get("customer_id") and not r.get("synthetic_customer")}),
    }

    # ---- lớp 3: khung diễn biến + 8-gram (8-gram chỉ hỗ trợ phát hiện, không chứng minh khác template)
    fam_sk = collections.defaultdict(set)
    for r in new:
        fam_sk[r["family"]].add(r["skeleton"])
    old_sk = collections.defaultdict(set)
    for r in old:
        old_sk[f"{r['dataset_id']}@{r['version']}/{r['part']}:{r['template_id'] or r['scenario_id']}"].add(r["skeleton"])
    fam_rep = {}
    for fam, sks in sorted(fam_sk.items()):
        best = []
        for name, osk in old_sk.items():
            inter = len(sks & osk)
            if inter:
                best.append((round(inter / len(sks | osk), 2), inter, name))
        best.sort(reverse=True)
        fam_rep[fam] = {"skeletons": sorted(sks), "identical_skeleton_in_old": [n for j, i, n in best if i == len(sks)][:8],
                        "top_overlap": [{"jaccard": j, "shared": i, "old": n} for j, i, n in best[:5]]}
    rep["layer3_structure"] = fam_rep
    grams_by_part = collections.defaultdict(set)
    for r in old:
        sc = json.load(open(os.path.join(ROOT, r["file"]), encoding="utf-8"))
        tag = f"{r['dataset_id']}@{r['version']}/{r['part']}"
        for t in customer_turns(sc):
            grams_by_part[tag] |= _ngrams(t)
    ng = {}
    for tag, grams in sorted(grams_by_part.items()):
        hits = [(sid, t) for sid, t in new_turns if _ngrams(t) & grams]
        shared = collections.Counter(" ".join(g) for _, t in hits for g in (_ngrams(t) & grams))
        ng[tag] = {"new_turns_with_shared_8gram": len(hits), "of": len(new_turns),
                   "top_shared": [] if tag in text_unopened else shared.most_common(5)}
    rep["layer3_8gram"] = ng

    # ---- coverage release mới
    sc_new = [json.load(open(os.path.join(ROOT, r["file"]), encoding="utf-8")) for r in new]
    pol = collections.Counter(r.get("polarity") or "pos" for r in new)
    key_neg = sum(1 for sc in sc_new if any((c.get("success_if") or {}).get("must_not_call_tools") for c in sc["calls"].values()))
    abstain = sum(1 for sc in sc_new if any("agent_must_say" in (c.get("success_if") or {}) for c in sc["calls"].values()))
    tools = collections.Counter(str((c.get("success_if") or {}).get("tool_called")) for sc in sc_new for c in sc["calls"].values() if c.get("success_if"))
    rep["coverage"] = {
        "families": len({r["family"] for r in new}), "groups": dict(collections.Counter(r.get("group") for r in new)),
        "polarity": dict(pol), "scenarios_with_must_not_call_tools": key_neg, "scenarios_with_abstain": abstain,
        "n_calls": dict(collections.Counter(r["n_calls"] for r in new)),
        "multi_session_ratio": round(sum(r["n_calls"] >= 2 for r in new) / len(new), 3),
        "channels": dict(collections.Counter(ch for r in new for ch in r["channels"])),
        "input_modes": dict(collections.Counter(m for r in new for m in r["input_modes"])),
        "graded_tools": dict(tools), "hard_case": dict(collections.Counter(r["hard_case"] for r in new)),
        "skus": dict(collections.Counter(s for sc in sc_new for c in sc["calls"].values()
                                         for s in [((c.get("success_if") or {}).get("args_match") or {}).get("sku")] if s)),
    }

    # ---- canary đúng / rỗng / sai có chủ ý qua reference_eval của BTC
    ev, mt = _load_eval(), _mock()
    rep["canary"] = canary(sc_new, ev, mt)
    os.makedirs(a.out, exist_ok=True)
    json.dump(rep, open(os.path.join(a.out, "audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    c = rep["canary"]
    print(json.dumps({"n": len(new), "layer1": {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in rep["layer1_exact"].items()},
                      "phone_reused_crm_or_synthetic": len(rep["layer2_lineage"]["phone_reused_from_old"]),
                      "synthetic_phone_reused": rep["layer2_lineage"]["synthetic_phone_reused_from_old"],
                      "families_with_identical_old_skeleton": [f for f, v in fam_rep.items() if v["identical_skeleton_in_old"]],
                      "coverage": {k: rep["coverage"][k] for k in ("families", "polarity", "scenarios_with_must_not_call_tools",
                                                                  "multi_session_ratio", "n_calls")},
                      "canary": {k: c[k] for k in ("n", "perfect_pass", "empty_fail", "wrong_fail")}, "canary_problems": c["problems"][:10]},
                     ensure_ascii=False, indent=1))
    gate = (c["perfect_pass"] == c["n"] == c["empty_fail"] == c["wrong_fail"] and not rep["layer1_exact"]["file_sha_dup_with_old"]
            and not rep["layer1_exact"]["scenario_text_dup_with_old"] and not rep["layer2_lineage"]["scenario_id_collision_with_old"]
            and not rep["layer2_lineage"]["synthetic_phone_reused_from_old"] and len(c["problems"]) == 0)
    print("AUDIT GATE:", "PASS" if gate else "FAIL")
    sys.exit(0 if gate else 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index")
    p.add_argument("--lock")
    p.add_argument("--index")
    sub.add_parser("suites")
    p = sub.add_parser("materialize")
    p.add_argument("--suite", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--allow-guarded", action="store_true")
    p = sub.add_parser("audit")
    p.add_argument("--release", required=True, help="dataset_id@version, vd h13@r1")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    {"index": cmd_index, "suites": cmd_suites, "materialize": cmd_materialize, "audit": cmd_audit}[a.cmd](a)


if __name__ == "__main__":
    main()
