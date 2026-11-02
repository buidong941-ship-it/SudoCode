"""Qwen naturalizer request shape and fact anchors without a live model."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datagen.naturalize import anchors_kept, rewrite_call  # noqa: E402


class Client:
    def __init__(self):
        self.chat = SimpleNamespace(completions=self)
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"turns": ["À, cho chị hỏi AirPure X giá 5 triệu nhé."]}, ensure_ascii=False)))])


def run():
    original = "Chị hỏi AirPure X giá 5 triệu."
    c = Client()
    out = rewrite_call({"honorific": "chị", "persona": "khach_so_gia"}, "call_1",
                       {"customer_turns": [original]}, {}, c, "Qwen/Qwen3-4B", .7,
                       {"chat_template_kwargs": {"enable_thinking": False}})
    assert out == ["À, cho chị hỏi AirPure X giá 5 triệu nhé."]
    assert c.kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    d = Client()
    rewrite_call({"honorific": "chị", "persona": "khach_so_gia"}, "call_1",
                 {"customer_turns": [original]}, {}, d, "deepseek-v4-flash", .7)
    assert "extra_body" not in d.kwargs
    assert anchors_kept(original, out[0])[0]
    assert not anchors_kept(original, "À, cho chị hỏi AirPure X giá 6 triệu nhé.")[0]
    claude_backend()
    print("naturalize backend checks OK")


def claude_backend():
    """D-7: --backend claude không gọi API — chưa có cache thì ghi claude_todo.jsonl; --import-claude gộp lời Claude viết
    (khóa claude:<băm>) rồi chạy --offline dùng đúng lời đó; lời làm mất số / tên riêng bị loại (giữ câu gốc)."""
    import subprocess
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="nat_claude_"))
    (tmp / "src" / "dev").mkdir(parents=True)
    sc = {"scenario_id": "T-1", "persona": "khach_so_gia", "honorific": "chị",
          "calls": {"call_1": {"channel": "hotline", "customer_turns": ["Chị hỏi AirPure X giá 5 triệu.", "Để chị tính."]}}}
    (tmp / "src" / "dev" / "T-1.json").write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
    nat = [sys.executable, str(ROOT / "datagen" / "naturalize.py"), "--src", str(tmp / "src"), "--out", str(tmp / "out"),
           "--splits", "dev", "--backend", "claude"]
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(nat, capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(ROOT))
    todo = [json.loads(l) for l in (tmp / "out" / "claude_todo.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert r.returncode == 0 and len(todo) == 1 and todo[0]["key"].startswith("claude:"), (r.stdout, r.stderr)
    rewrites = {todo[0]["key"]: ["Dạ chị hỏi thử AirPure X giá 5 triệu đó em.", "Ờ để chị tính đã nha."]}
    (tmp / "claude.json").write_text(json.dumps(rewrites, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(nat + ["--offline", "--import-claude", str(tmp / "claude.json")], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=str(ROOT))
    out = json.loads((tmp / "out" / "dev" / "T-1.json").read_text(encoding="utf-8"))
    assert r.returncode == 0 and out["calls"]["call_1"]["customer_turns"] == rewrites[todo[0]["key"]], (r.stdout, r.stderr, out)
    bad = {todo[0]["key"]: ["Chị hỏi máy giá 6 triệu.", "Để chị tính."]}
    (tmp / "bad.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    subprocess.run(nat + ["--offline", "--import-claude", str(tmp / "bad.json")], capture_output=True, env=env, cwd=str(ROOT))
    out = json.loads((tmp / "out" / "dev" / "T-1.json").read_text(encoding="utf-8"))
    assert out["calls"]["call_1"]["customer_turns"][0] == "Chị hỏi AirPure X giá 5 triệu.", out


if __name__ == "__main__":
    run()
