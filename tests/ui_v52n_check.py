"""Kiểm UI nối cấu hình chính B2-v52n (17/11, không API): profile mặc định là b2_v52n; env profile GIỐNG HỆT env đã kiểm (b2_v51a /
config snapshot v52n); nhãn nêu B2-v52n; kiểm hash code theo freeze của profile (khớp → chạy; lệch → startup_check từ chối, nhãn
cảnh báo); profile b2_v51a vẫn chọn được để đối chiếu. Hành vi hội thoại / C.5 của UI do tests/ui_b2_check.py kiểm (không đổi).

Chạy: python tests/ui_v52n_check.py   (Kaggle CPU; cần runs/freeze/20261117-v52n-ui2/code_sha256.txt (bản vá UI 17/11) và
runs/snapshots/20261117-b2-v52n/config.json — job có --include hai tệp này)"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(prefix="uiv52n_")
os.environ.pop("UI_PROFILE", None)                           # mặc định phải là b2_v52n
os.environ["UI_QWEN"] = "off"
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "ui.db").replace("\\", "/")
os.environ["LLM_CACHE"] = "off"

from ui import engine as E  # noqa: E402

FAILS = []


def ok(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


prof = json.load(open(os.path.join(ROOT, "profiles", "b2_v52n.json"), encoding="utf-8"))
old = json.load(open(os.path.join(ROOT, "profiles", "b2_v51a.json"), encoding="utf-8"))
ok(E.PROFILE == "b2_v52n" and E.PROFILE_INFO["profile"] == "b2_v52n", f"profile mặc định b2_v52n: {E.PROFILE_INFO['profile']}")
ok(prof["env"] == old["env"], "env b2_v52n giống hệt b2_v51a (env job API v52n đã kiểm)")
ok(prof["freeze"] == "runs/freeze/20261117-v52n-ui2" and prof["core_freeze"] == "runs/freeze/20261117-v52n-cand", "profile khai đúng freeze")
snap = os.path.join(ROOT, prof["snapshot"], "config.json")
ok(os.path.exists(snap) and E.PROFILE_INFO["profile_drift"] == [], f"profile khớp config snapshot v52n: drift={E.PROFILE_INFO['profile_drift']}")
code = E.PROFILE_INFO["code"]
ok(code["status"] == "ok" and code["checked"] >= 250, f"code khớp freeze v52n-ui2: {code['status']} {code['checked']} lệch={code['bad'][:5]}")
info = E.startup_check()
ok(info["ok"] and info["arch"] == "target" and info["planner_variant"] == "b2_jev", f"startup_check: {info}")
ok("B2-v52n" in info["label"] and "khác cấu hình đo" in info["label"] and "CẢNH BÁO" not in info["label"], f"nhãn: {info['label']}")
ok(info["code"]["status"] == "ok", "startup_check báo trạng thái code")

# lệch code → từ chối (freeze giả có một hash sai; không sửa tệp thật)
fake = os.path.join(tmp, "fz")
os.makedirs(fake)
lines = open(os.path.join(ROOT, prof["freeze"], "code_sha256.txt"), encoding="utf-8").read().splitlines()
lines[0] = "0" * 64 + "  " + lines[0].split(None, 1)[1]
open(os.path.join(fake, "code_sha256.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
bad = E.code_check(os.path.relpath(fake, ROOT))
ok(bad["status"] == "mismatch" and len(bad["bad"]) == 1, f"freeze sai một hash → mismatch: {bad['status']} {bad['bad']}")
saved = E.PROFILE_INFO["code"]
E.PROFILE_INFO["code"] = bad
rej = E.startup_check()
ok(not rej["ok"] and any("code lệch freeze" in m for m in rej["mismatch"]), "code lệch → startup_check từ chối")
E.PROFILE_INFO["code"] = saved
ok(E.code_check("runs/freeze/khong-co")["status"] == "absent", "không có tệp freeze → absent (nhãn ghi chưa kiểm)")

# profile đối chiếu b2_v51a vẫn chọn được (tiến trình riêng: profile chọn một lần lúc import)
r = subprocess.run([sys.executable, "-c", "import json,sys; sys.path.insert(0, '.'); from ui import engine as E; "
                    "print(json.dumps({'p': E.PROFILE_INFO['profile'], 'l': E.PROFILE_INFO['label']}, ensure_ascii=False))"],
                   cwd=ROOT, capture_output=True, text=True, env={**os.environ, "UI_PROFILE": "b2_v51a", "PYTHONIOENCODING": "utf-8"})
got = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else {}
ok(got.get("p") == "b2_v51a" and "B2-v51-A" in got.get("l", ""), f"UI_PROFILE=b2_v51a vẫn chạy: {got or r.stderr[-300:]}")
r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, '.'); from ui import engine"], cwd=ROOT, capture_output=True,
                   text=True, env={**os.environ, "UI_PROFILE": "khong_co"})
ok(r.returncode != 0 and "không hỗ trợ" in r.stderr, "profile lạ bị từ chối")

print("\n" + ("ĐẠT" if not FAILS else f"KHÔNG ĐẠT: {len(FAILS)}"))
sys.exit(1 if FAILS else 0)
