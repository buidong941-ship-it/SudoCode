"""Thử key Jev: gửi 1 câu ngắn (không có dữ liệu khách) tới System One và in kết quả. Không in key."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import settings  # noqa: E402

print("base_url:", settings.jev_base_url or "(mặc định api.typesafe.ai)", "| model:", settings.jev_model,
      "| có key:", bool(settings.typesafe_api_key))
from typesafe_sdk import Choice, TypeSafeClient  # noqa: E402

client = TypeSafeClient(api_key=settings.typesafe_api_key, timeout=30, model=settings.jev_model,
                        base_url=settings.jev_base_url)
try:
    print("models:", str(client.models())[:800])
except Exception as exc:
    print(f"models: LỖI {type(exc).__name__}: {str(exc)[:200]}")
ok = 0
for i in range(3):
    t = time.perf_counter()
    try:
        r = client.system_one(state={"cau": "Shop ơi máy lọc nước này giá bao nhiêu?"},
                              questions={"y_dinh": Choice(instructions="Câu này hỏi gì?",
                                                          criteria={"gia": "hỏi giá", "khac": "khác"})},
                              model=settings.jev_model)
        print(f"lần {i + 1}: OK {r.choices['y_dinh'].choice} ({time.perf_counter() - t:.2f}s)")
        ok += 1
    except Exception as exc:
        print(f"lần {i + 1}: LỖI {type(exc).__name__}: {str(exc)[:200]}")
print("KẾT QUẢ:", f"{ok}/3 thành công")
