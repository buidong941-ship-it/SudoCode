"""Dò đường trích slot lịch gọi lại (không gọi model): luật, CERT, Jev giả định các nhãn, nhánh Qwen giả định. Chạy trên Kaggle CPU."""
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import settings  # noqa: E402
from harness import extractor as X, jev_hybrid, llm_extract as LX  # noqa: E402

TEXTS = ["Giờ chị bận rồi, mai 17 giờ em gọi lại giúp chị nhé.", "Mai 9 giờ em gọi lại cho cô nha, giờ cô đang bận.",
         "ok, để anh tính thêm, mai mốt anh gọi lại."]
out = []
for text in TEXTS:
    rules = X.customer_slots_rules(text, "2026-10-15")
    row = {"text": text, "rules": rules, "candidate": X.customer_llm_candidate(text, "ctx")}
    for labels in ([], ["callback_requested"]):
        for qwen in ({}, {"callback_requested": "2026-10-16T17:00"}):
            meta = {}
            with patch.object(settings, "extractor_backend", "hybrid"), patch.object(settings, "extractor_confidence_gate", True), \
                    patch.object(settings, "extractor_jev_hybrid", True), patch.object(settings, "extractor_no_jev", False), \
                    patch.object(settings, "extractor_async", True), patch.object(jev_hybrid, "labels", return_value=set(labels)), \
                    patch.object(LX, "customer_slots", side_effect=lambda t, d, r, m, meta=None, context=None, q=qwen: {**r, **q}):
                slots, pending = X.customer_slots_start(text, "2026-10-15", meta=meta, context="Nhân viên: ...")
                late = X.customer_slots_finish(pending, slots, 30) if pending is not None else None
            row[f"jev={labels} qwen={sorted(qwen)}"] = {"slots": slots, "late": late, "pending": pending is not None,
                                                         **{k: meta.get(k) for k in ("backend", "jev_dropped_rule_slots", "jev_empty_overridden",
                                                                                     "qwen_arbitrated_slots", "single_source_dropped")},
                                                         "cert": (meta.get("customer_confidence") or {}).get("certified"),
                                                         "empty_cert": (meta.get("customer_empty_confidence") or {}).get("certified")}
    out.append(row)
os.makedirs(sys.argv[1], exist_ok=True)
json.dump(out, open(os.path.join(sys.argv[1], "callback_route.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str)[:6000])
