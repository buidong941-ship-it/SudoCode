"""Lớp chạy agent cho UI — gọi core đúng như `run_eval.py`, không sửa core, không dùng chung DB với lần chạy đo.

Tách biệt:
- core (harness/, core/, eval/) không import ui/ (tests/ui_check.py kiểm tra);
- UI có DB bộ nhớ riêng `data/ui/memory.db` (đặt env `DATABASE_URL` khác nếu muốn) và namespace riêng `ui:<config>:<tên demo>`,
  nên không đụng `data/memory.db` hay namespace của run_eval;
- env phải đặt TRƯỚC khi import harness (settings đọc env lúc import), nên module này đặt mặc định ở đầu file và chỉ
  import harness bên trong hàm.
"""
import json
import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

UI_DB = os.path.join(ROOT, "data", "ui", "memory.db")
os.environ.setdefault("RUN_PROFILE", "local")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + UI_DB.replace("\\", "/"))
os.environ.setdefault("TOOL_TRANSPORT", "direct")
os.environ.setdefault("RAG_MODE", "bm25")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

CHANNELS = ["hotline", "zalo_oa", "chat_fanpage"]

# Kịch bản demo C.6 (đề bài): cuộc 1 tư vấn + báo giá + KM, hẹn hỏi người nhà; cuộc 2 vài ngày sau chốt đơn;
# cuộc 3 (M2) gọi lại hỏi vận đơn. Lời khách viết tay cho demo, không lấy từ bộ test.
DEMO_PHONE = "0987650123"
DEMO_SCRIPT = [
    {"call": "call_1", "days_later": 0, "turns": [
        "Chào em, anh đang tìm máy lọc không khí cho phòng ngủ khoảng 30 mét vuông.",
        "Máy AirPure Y giá bao nhiêu em, có khuyến mãi gì không?",
        "Ừ để anh hỏi ý vợ đã rồi tính nhé, cuối tuần anh gọi lại.",
    ]},
    {"call": "call_2", "days_later": 3, "turns": [
        "Alo em, anh gọi lại vụ máy lọc không khí hôm trước.",
        "Nhà anh đồng ý rồi, em lên đơn cho anh nhé.",
        "Giao về số 12 Nguyễn Trãi, Thanh Xuân, Hà Nội giúp anh.",
    ]},
    {"call": "call_3", "days_later": 5, "turns": [
        "Em ơi đơn máy lọc không khí của anh giao tới đâu rồi?",
    ]},
]


def _imports():
    from core.llm.generator import Generator
    from core.llm.router import Router
    from harness.agent import CallSession
    from harness.memory import open_memory
    from harness.tools import ToolBox
    return Generator, Router, CallSession, open_memory, ToolBox


class Engine:
    """Một "khách demo" = một namespace bộ nhớ. Mỗi cuộc gọi tạo một CallSession mới trên cùng namespace."""

    def __init__(self, name="demo", config="full", router="rules", generator="offline", start_date="2026-10-15"):
        Generator, Router, _, open_memory, ToolBox = _imports()
        self.name, self.config = name, config
        self.ns = f"ui:{config}:{name}"
        self.mem = open_memory(self.ns, read_enabled=(config == "full"))
        self.router, self.gen = Router(router), Generator(generator)
        self.start_date = start_date
        self.sess, self.calls, self.n_calls = None, [], 0
        self._ToolBox = ToolBox

    # ---------- vòng đời ----------
    def reset(self):
        """Xoá bộ nhớ của namespace này và trạng thái mock (đơn đã tạo, tồn kho)."""
        self.end_call()
        self.mem.wipe()
        self._ToolBox.reset_world()
        self.calls, self.n_calls = [], 0

    def start_call(self, phone, channel="hotline", day=None, channel_identity=None, input_mode="text"):
        _, _, CallSession, _, _ = _imports()
        self.end_call()
        self.n_calls += 1
        day = day or self.start_date
        name = f"call_{self.n_calls}"
        self.sess = CallSession(memory=self.mem, today=day, call_name=name, session_id=f"{self.name}:{name}",
                                channel=channel, channel_identity=channel_identity,
                                phone=phone if channel == "hotline" or not channel_identity else None,
                                input_mode=input_mode, router=self.router, generator=self.gen, config=self.config)
        brief = self.sess.start()
        self.calls.append({"call": name, "date": day, "channel": channel, "brief": brief, "turns": []})
        return brief

    def say(self, text):
        if self.sess is None:
            raise RuntimeError("chưa bắt đầu cuộc gọi")
        row = self.sess.turn(text)
        self.calls[-1]["turns"].append(row)
        return row

    def end_call(self):
        if self.sess is not None:
            self.sess.end()
            self.sess = None

    # ---------- đọc bộ nhớ (chỉ đọc, thẳng từ DB) ----------
    def customer_id(self):
        if self.sess and self.sess.customer:
            return self.sess.customer["customer_id"]
        for c in reversed(self.calls):
            cid = (c["brief"] or {}).get("customer_phone")
            if cid:
                ids = self.mem.lookup("phone", cid)
                if ids:
                    return ids[0]
        return None

    def timeline(self, customer_id=None):
        """Dòng thời gian bộ nhớ: phiên + fact (kể cả fact đã bị thay thế, có nguồn) + báo giá, sắp theo ngày."""
        from sqlalchemy import and_, select
        from harness import memory as M
        cid = customer_id or self.customer_id()
        if not cid or not hasattr(self.mem, "e"):
            return []
        ev = []
        with self.mem.e.connect() as c:
            for r in c.execute(select(M.sessions).where(and_(M.sessions.c.ns == self.ns, M.sessions.c.customer_id == cid))).mappings():
                ev.append({"date": r["started_on"], "kind": "phiên", "what": f"{r['session_id']} · {r['channel']} · {r['outcome']}",
                           "detail": r["summary"], "source": r["source"], "status": ""})
            for r in c.execute(select(M.facts).where(and_(M.facts.c.ns == self.ns, M.facts.c.customer_id == cid))
                               .order_by(M.facts.c.fact_id)).mappings():
                ev.append({"date": r["valid_from"], "kind": "fact", "what": r["slot"],
                           "detail": json.loads(r["value_json"]), "source": r["source"],
                           "status": r["status"] + (f" → #{r['superseded_by']}" if r["superseded_by"] else "")
                           + f" · hết hạn {r['expires_on']}", "fact_id": r["fact_id"]})
            for r in c.execute(select(M.quotes).where(and_(M.quotes.c.ns == self.ns, M.quotes.c.customer_id == cid))
                               .order_by(M.quotes.c.quote_id)).mappings():
                ev.append({"date": r["quoted_on"], "kind": "báo giá", "what": f"{r['sku']} ({r['role']})",
                           "detail": {"giá": r["final_price_vnd"], "KM": r["promo_code"], "KM hết hạn": r["promo_end"]},
                           "source": r["session_id"], "status": ""})
        order = {"phiên": 0, "báo giá": 1, "fact": 2}
        return sorted(ev, key=lambda e: (e["date"] or "", order[e["kind"]]))

    # ---------- demo C.6 ----------
    def run_demo(self, upto=None, phone=DEMO_PHONE):
        """Chạy kịch bản C.6 từ đầu (reset trước). `upto` = số cuộc gọi muốn chạy (mặc định tất cả)."""
        self.reset()
        d0 = date.fromisoformat(self.start_date)
        for c in DEMO_SCRIPT[:upto]:
            self.start_call(phone, "hotline", (d0 + timedelta(days=c["days_later"])).isoformat())
            for t in c["turns"]:
                self.say(t)
            self.end_call()
        return self.calls


def reports(base=os.path.join(ROOT, "runs")):
    """Tìm các report.json của reference_eval dưới runs/ (để hiện bảng full so với baseline)."""
    out = []
    for d, _, fs in os.walk(base):
        for f in fs:
            if f == "report.json" or f.endswith(".report.json"):
                out.append(os.path.join(d, f))
    return sorted(out, key=os.path.getmtime, reverse=True)


METRIC_ROWS = [("Repeat-Question Rate (%)", "repeat_question_rate", "value"),
               ("Context Carryover Rate (%)", "context_carryover_rate", "value"),
               ("Task Success Rate (%)", "task_success_rate", "value"),
               ("Hallucination giá & KM (%)", "hallucination_rate", "price_promo_only.value"),
               ("Số lượt TB / cuộc", "avg_turns_per_call", None),
               ("Vi phạm guardrail", "guardrail_violations", "total")]


def _dig(d, path):
    for k in (path or "").split(".") if path else []:
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return d


def metric_table(report):
    """→ [(tên chỉ số, baseline, hệ thống)] từ report.json của eval/reference_eval.py."""
    rows = []
    for title, key, path in METRIC_ROWS:
        vals = []
        for side in ("baseline", "system"):
            v = (report.get(side) or {}).get(key)
            v = _dig(v, path) if path else (v.get("value") if isinstance(v, dict) else v)
            vals.append(v)
        rows.append((title, *vals))
    return rows
