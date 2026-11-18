"""Ghi lại demo C.6 hai cuộc gọi (khách mới → khách quay lại) thành transcript markdown + JSON, chạy trên Kaggle.

    python scripts/demo_record.py <out_dir>

Dùng đúng ui/engine.py (kịch bản DEMO_SCRIPT viết riêng cho demo, không lấy từ bộ test). Backend router/generator theo cấu hình
môi trường (CPU: rules + offline; GPU: jev giả lập + qwen). Reset bộ nhớ demo trước khi chạy.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ui import engine as E  # noqa: E402


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    eng = E.Engine("demo-record")
    calls = eng.run_demo(upto=2)
    md = ["# Demo C.6: hai cuộc gọi (ghi tự động)", ""]
    for i, c in enumerate(calls, 1):
        b = c["brief"]
        md += [f"## Cuộc {i} ({'khách quay lại' if b.get('is_returning') else 'khách mới'})", ""]
        if b.get("is_returning"):
            md += [f"Call Brief: {b.get('last_session', {}).get('summary', '')}", f"Không hỏi lại: {', '.join(b.get('must_not_ask') or [])}", ""]
        for r in c["turns"]:
            tools = ", ".join(t["name"] for t in r.get("tool_calls") or [])
            md += [f"- **Khách:** {r['customer_text']}", f"  - **Agent:** {r['agent_text']}",
                   f"  - goals `{', '.join(r['goals'])}`" + (f" · tool `{tools}`" if tools else ""), ""]
    md += ["## Dòng thời gian bộ nhớ", ""] + [f"- {e['date']} · {e['kind']} · {e['what']}" for e in eng.timeline()]
    open(os.path.join(out, "demo_c6.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    json.dump(calls, open(os.path.join(out, "demo_c6.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"đã ghi {len(calls)} cuộc → {out}")


if __name__ == "__main__":
    main()
