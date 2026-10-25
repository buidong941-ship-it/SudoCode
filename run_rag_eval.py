#!/usr/bin/env python3
"""Chấm phần RAG trên bộ câu hỏi có nhãn của BTC (rag/qa_labeled.json) → rag_results.json + bảng Recall@k / abstain.

    python run_rag_eval.py --download                      # tải model embedding một lần (EMBED_MODEL)
    python run_rag_eval.py --out runs/rag/rag_results.json # truy hồi + sinh câu trả lời (DeepSeek) + chấm
    python run_rag_eval.py --no-generate                   # chỉ truy hồi (không cần khóa API): Recall@k, abstain theo luật
    python run_rag_eval.py --mode bm25                     # so sánh: chỉ BM25
    python eval/reference_eval.py ... --rag runs/rag/rag_results.json   # BTC chấm lại bằng script của họ

Định dạng rag_results.json (BTC): {qid: {"retrieved_chunk_ids": [...], "abstained": bool, "answer": "..."}}.

`abstained`: LLM chỉ được trả lời từ các chunk ĐƯỢC PHÉP trong top-k (chunk tài liệu nội bộ bị giữ lại, không bao giờ gửi
ra ngoài) và phải tự báo `abstain` khi các chunk đó không chứa câu trả lời. Vì vậy câu hỏi dò giá nhập / nhà cung cấp tự động
thành "không có thông tin để cung cấp"; nếu chunk đứng đầu là tài liệu nội bộ thì lời từ chối nói rõ đó là thông tin nội bộ.
Với `--no-generate`: từ chối khi chunk đứng đầu là nội bộ, hoặc độ tương tự vector dưới `--min-dense` (kém chính xác hơn).
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

ANSWER_PROMPT = """Bạn là nhân viên tư vấn của shop. Trả lời câu hỏi của khách CHỈ dựa trên các đoạn chính sách dưới đây.
- Nếu các đoạn không chứa thông tin để trả lời, hoặc chính đoạn đó nói shop không có thông tin: đặt "abstain": true và trả lời "Dạ em chưa có thông tin về vấn đề này".
- Không suy đoán, không dùng kiến thức ngoài. Trả lời 1–2 câu, nêu con số đúng như trong đoạn.
- Ngày hôm nay: {today}. Nếu đoạn nhật ký thay đổi cho biết quy định cũ đã bị thay, trả lời theo quy định đang hiệu lực.

Câu hỏi: {q}

Các đoạn chính sách:
{ctx}

Trả về JSON: {{"answer": "...", "abstain": true|false}}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qa", default=os.path.join(ROOT, "rag", "qa_labeled.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "rag", "rag_results.json"))
    ap.add_argument("--mode", choices=["auto", "hybrid", "bm25"], help="ghi đè RAG_MODE")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("--min-dense", type=float, default=0.0, help="với --no-generate: dưới ngưỡng này thì coi là không có thông tin")
    ap.add_argument("--download", action="store_true", help="tải model embedding (EMBED_MODEL) và reranker (RERANK_MODEL) về máy rồi thoát")
    a = ap.parse_args()
    if a.mode:
        os.environ["RAG_MODE"] = a.mode
    if a.download:
        os.environ["RAG_ALLOW_DOWNLOAD"] = "1"; os.environ["RAG_MODE"] = "hybrid"
    from core.config import settings
    from harness import rag
    if a.download:
        print("đã sẵn sàng:", json.dumps(rag.describe(), ensure_ascii=False))
        return 0

    qa = json.load(open(a.qa, encoding="utf-8"))["questions"]
    gen = None
    if not a.no_generate:
        from openai import OpenAI
        if not settings.deepseek_api_key:
            sys.exit("DEEPSEEK_API_KEY chưa đặt (hoặc dùng --no-generate)")
        gen = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, timeout=60, max_retries=2)
    res, lat = {}, []
    for q in qa:
        t0 = time.perf_counter()
        hits = rag.retrieve(q["question"], k=a.k)
        lat.append((time.perf_counter() - t0) * 1000)
        r = {"retrieved_chunk_ids": [h["chunk_id"] for h in hits], "abstained": False, "answer": ""}
        allowed = [h for h in hits if not h["restricted"]]
        top_restricted = bool(hits and hits[0]["restricted"])
        if gen is None:
            top = max((h["dense"] or 0) for h in hits) if hits else 0
            r["abstained"] = not hits or top_restricted or (rag.mode() == "hybrid" and top < a.min_dense)
        else:
            ctx = "\n\n".join(f"[{h['chunk_id']}] {h['title']}\n{h['text']}" for h in allowed)
            try:
                o = gen.chat.completions.create(model=settings.deepseek_model, temperature=0, max_tokens=1200,
                                                response_format={"type": "json_object"},
                                                messages=[{"role": "system", "content": "Chỉ trả về JSON hợp lệ."},
                                                          {"role": "user", "content": ANSWER_PROMPT.format(q=q["question"], ctx=ctx, today="2026-10-15")}])
                j = json.loads(o.choices[0].message.content or "{}")
                r["answer"], r["abstained"] = str(j.get("answer", "")), bool(j.get("abstain"))
                if r["abstained"] and top_restricted:
                    r["answer"] = "Dạ thông tin này là thông tin nội bộ, em không cung cấp được ạ."
            except Exception as e:
                r["answer"], r["error"] = "", f"{type(e).__name__}: {str(e)[:150]}"
        res[q["qid"]] = r
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    sys.path.insert(0, os.path.join(ROOT, "eval"))
    from reference_eval import rag_eval
    m = rag_eval(a.qa, a.out)
    lat.sort()
    meta = {**rag.describe(), "generate": gen is not None, "llm": settings.deepseek_model if gen else None,
            "retrieval_ms_p50": round(lat[len(lat) // 2], 1), "retrieval_ms_max": round(lat[-1], 1), "metrics": m}
    json.dump(meta, open(os.path.splitext(a.out)[0] + ".report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"mode={meta['mode']} model={meta['embed_model']} reranker={meta['reranker']} kho={meta['store']} thiết bị={meta['device']} "
          f"chunks={meta['n_chunks']} truy hồi p50={meta['retrieval_ms_p50']}ms")
    for k in ("recall@3", "recall@5", "multi_hop_full_recall@3", "multi_hop_full_recall@5", "abstain_rate_unanswerable",
              "abstain_rate_restricted", "false_abstain_rate"):
        print(f"  {k:<28}{m[k]}")
    print("  by_type_recall@5            ", m["by_type_recall@5"])
    miss = [(q["qid"], q["type"], q["relevant_chunk_ids"], res[q["qid"]]["retrieved_chunk_ids"]) for q in qa
            if q["relevant_chunk_ids"] and not set(q["relevant_chunk_ids"]) & set(res[q["qid"]]["retrieved_chunk_ids"][:5])]
    for x in miss:
        print("  trượt @5:", x)
    print("→", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
