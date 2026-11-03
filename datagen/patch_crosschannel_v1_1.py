"""B3 (PLAN-2026-11-01): vá benchmark BTC-like v1 → v1_1 cho họ `delivery_address` (fanpage → hotline).

Lỗi: template dùng khách tổng hợp (không có trong CRM) chat fanpage ở cuộc 1, rồi gọi hotline bằng SĐT ở cuộc 2. Khách chưa
từng cho SĐT trong cuộc chat nên không có cách hợp lệ nào nối hai kênh → ca KHÔNG THỂ qua dù agent làm đúng (BTCL-016/017
và các ca holdout cùng họ). Ca tương ứng của BTC (SAMPLE-04) dùng khách có trong CRM kèm fb_id.

Cách vá (giữ nguyên lời thoại, sản phẩm, ngày, địa chỉ, đáp án): đổi khách sang một khách CRM có fb_id, không có đơn,
không có lịch sử, không dùng chung SĐT, không trùng khách của public_sample — y như `customers(kind='crm', need=['fb_id'])`
mà template đã sửa sẽ chọn. Các trường đổi: customer_phone, customer_name, honorific, calls.call_1.channel_identity,
_meta.customer_id / synthetic_customer / patched. Giá trong ground truth không đổi vì khách được chọn không sở hữu sản
phẩm nào (không kích hoạt KM trade-in).

Chống rò rỉ: script KHÔNG in lời thoại hay đáp án của bất kỳ scenario nào (kể cả holdout); chỉ in mã scenario đã vá.

    python datagen/patch_crosschannel_v1_1.py            # v1 → datagen/out_btc_like_final_v1_1 (bản v1 giữ nguyên)
    python datagen/patch_crosschannel_v1_1.py --src datagen/out_btc_like_final_v2 --dst datagen/out_btc_like_final_v2_1         --date 2026-11-02                                # D29: cùng bản vá cho v2 (lời khách viết lại tay)
"""
import glob
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "datagen", "out_btc_like_final_v1")
DST = os.path.join(ROOT, "datagen", "out_btc_like_final_v1_1")
HARD = "dia_chi_giao_hang_nhieu_phien"


def crm_pool():
    crm = json.load(open(os.path.join(ROOT, "catalog", "crm_seed.json"), encoding="utf-8"))
    crm = crm.get("customers", crm) if isinstance(crm, dict) else crm
    sample_phones = {json.load(open(f, encoding="utf-8")).get("customer_phone")
                     for f in glob.glob(os.path.join(ROOT, "test_set", "public_sample", "*.json"))}
    return [c for c in crm if c.get("fb_id") and not c.get("orders") and not c.get("sessions")
            and not c.get("shared_phone_with") and c["phone"] not in sample_phones]


def main():
    import argparse
    global SRC, DST
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--dst", default=DST)
    ap.add_argument("--date", default="2026-11-01")
    a = ap.parse_args()
    SRC, DST = os.path.join(ROOT, a.src), os.path.join(ROOT, a.dst)
    if not os.path.isdir(SRC):
        sys.exit(f"không thấy {SRC}")
    if os.path.exists(DST):
        sys.exit(f"{DST} đã tồn tại — xoá nếu muốn vá lại")
    shutil.copytree(SRC, DST)
    pool = crm_pool()
    used = set()
    patched = []
    for split in ("dev", "holdout"):
        for f in sorted(glob.glob(os.path.join(DST, "final", split, "*.json"))):
            s = json.load(open(f, encoding="utf-8"))
            if s.get("hard_case") != HARD or not (s.get("_meta") or {}).get("synthetic_customer"):
                continue
            want = "chị" if s.get("honorific") in ("chị", "cô") else s.get("honorific")
            cand = [c for c in pool if c["honorific"] == want and c["customer_id"] not in used] or \
                   [c for c in pool if c["customer_id"] not in used]
            if not cand:
                sys.exit("hết khách CRM phù hợp")
            c = cand[0]
            used.add(c["customer_id"])
            old = {"customer_phone": s.get("customer_phone"), "customer_id": s["_meta"].get("customer_id")}
            s["customer_phone"], s["customer_name"], s["honorific"] = c["phone"], c["name"], c["honorific"]
            first = next(iter(s["calls"].values()))
            if first.get("channel") == "chat_fanpage":
                first["channel_identity"] = c["fb_id"]
            s["_meta"].update(customer_id=c["customer_id"], synthetic_customer=False,
                              patched={"by": "datagen/patch_crosschannel_v1_1.py", "date": a.date,
                                       "reason": "B3: khách đa kênh fanpage→hotline phải có trong CRM (fb_id) mới nối được",
                                       "old": old})
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(s, fh, ensure_ascii=False, indent=2)
            patched.append((split, s["scenario_id"], c["customer_id"]))
    m_path = os.path.join(DST, "manifest.json")
    m = json.load(open(m_path, encoding="utf-8"))
    m["patches"] = m.get("patches", []) + [{"date": a.date, "script": "datagen/patch_crosschannel_v1_1.py",
                                             "from": os.path.basename(SRC), "scenarios": [p[1] for p in patched],
                                             "reason": "B3 cross-channel identity"}]
    if isinstance((m.get("frozen") or {}).get("sha256"), dict):     # băm lại các file đã vá để manifest khớp nội dung
        import hashlib
        for split, sid, _ in patched:
            rel = f"final/{split}/{sid}.json"
            if rel in m["frozen"]["sha256"]:
                m["frozen"]["sha256"][rel] = hashlib.sha256(open(os.path.join(DST, rel), "rb").read()).hexdigest()
    json.dump(m, open(m_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for split, sid, cid in patched:
        print(f"vá {split}/{sid} → khách CRM {cid}")
    print(f"{len(patched)} scenario → {DST}")


if __name__ == "__main__":
    main()
