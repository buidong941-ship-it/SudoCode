"""Danh mục HÀNH ĐỘNG THẬT mà Jev được chọn (18/11, freeze integ-ui5) — dùng cho bước DeepSeek soạn nháp hướng dẫn từ feedback và cho
người duyệt. KHÔNG nằm trên đường chạy của agent (không module runtime nào import file này).

Nguồn: danh mục được dựng động mỗi lượt trong
  - harness/planner_b2.py `options(t)`          → tầng "main" (planner một tầng, cũng là đích khi B2-TT delegate);
  - harness/planner_b2tt.py `tasks(...)`         → tầng "outer" (B2-TT chọn tác vụ);
  - harness/planner_b2tt.py `inner_options(...)` → tầng "inner" (B2-TT chọn thao tác).
Ở đây ghi theo HỌ bước (tiền tố trước ':' / '@'). `catalog()` kèm sha256 của đúng các tệp nguồn đang nạp, và `check_source()` kiểm mọi
họ bước có trong mã nguồn đó (và ngược lại) — test tests/guidance_draft_check.py chạy kiểm này trên cùng phiên bản code.
Không phải danh sách MCP tool: Jev chọn các bước bọc bên ngoài; cột `tools` cho biết bước gọi tool nào bên trong.
"""
import hashlib
import os
import re

_H = os.path.dirname(os.path.abspath(__file__))
SOURCES = {"main": os.path.join(_H, "planner_b2.py"), "outer": os.path.join(_H, "planner_b2tt.py"), "inner": os.path.join(_H, "planner_b2tt.py")}

FAMILIES = [
    # ---------------------------------------------------------------- tầng main (planner_b2.options)
    {"step": "read_quote:<P#>", "tier": "main", "purpose": "đọc giá, khuyến mãi, tồn kho hiện tại của một mẫu đã gắn ref (bước 2: giá / KM phụ "
                                                  "thuộc biến thể chưa rõ → không công bố, trả lý do + trường thiếu)",
     "available": "mỗi mẫu có ref trong lượt; ẩn khi đã có bằng chứng trong lượt, khi mẫu ngoài phạm vi câu hỏi, hoặc khi khách vừa nêu "
                  "mẫu khác (chỉ giữ mẫu được nhắc)",
     "output": "lần báo giá đầu của lượt thành khối báo giá cho khách; mẫu khác đọc sau thành khối alternative_quote; lần báo giá đầu "
               "chạy đối chiếu mức giá khách nhắc (chỉ giải thích KM cũ khi có provenance)",
     "tools": ["pricing.get_quote", "inventory.check"], "writes": False},
    {"step": "read_stock:<P#|V#>", "tier": "main", "purpose": "chỉ đọc tồn kho (mẫu đã có giá, hoặc biến thể mới khi đổi đơn)",
     "available": "như read_quote; V# chỉ khi đang đổi biến thể của đơn", "output": "bằng chứng kho", "tools": ["inventory.check"], "writes": False},
    {"step": "read_order", "tier": "main", "purpose": "đọc các đơn của khách", "available": "luôn có (ẩn khi đã đọc trong lượt)",
     "output": "danh sách đơn (là câu trả lời nếu khách hỏi đơn)", "tools": ["order.status"], "writes": False},
    {"step": "check_window:<O#>", "tier": "main", "purpose": "kiểm hạn đổi / trả của một đơn theo chính sách ở ngày tạo đơn",
     "available": "sau khi đã đọc đơn", "output": "còn / quá hạn", "tools": [], "writes": False},
    {"step": "read_policy", "tier": "main", "purpose": "tìm đoạn chính sách cho câu khách (RAG tài liệu policy/)",
     "available": "luôn có", "output": "đoạn chính sách làm nguồn", "tools": [], "writes": False},
    {"step": "answer_ask:<nhãn hỏi>", "tier": "main", "purpose": "trả lời câu khách theo nhãn hỏi của bộ hiểu",
     "available": "mỗi nhãn hỏi còn chờ của lượt (price, promo, delivery_time, attribute, recommend, ...)",
     "output": "trả lời có nguồn, hoặc báo chưa có thông tin, hoặc câu hỏi lại khách khi câu hỏi chưa gắn được sản phẩm (bước tự hỏi; Jev "
               "không có bước 'hỏi khách' tự do)", "tools": ["tùy chủ đề: giá / kho / đơn / giỏ / chính sách / catalog"], "writes": False},
    {"step": "report_cart", "tier": "main", "purpose": "báo các món trong giỏ + tổng tiền", "available": "khi giỏ có món và giỏ đổi từ lần báo trước",
     "output": "khối giỏ hàng", "tools": ["pricing.quote_order"], "writes": False},
    {"step": "commit_request:<R#>[@P#]", "tier": "main", "purpose": "thực hiện yêu cầu giao dịch đang mở (đặt / đổi / trả / hủy / bổ sung địa chỉ)",
     "available": "mỗi yêu cầu đang mở; code kiểm lại quyền + bằng chứng và từ chối nếu chưa đủ",
     "output": "ghi một lần hoặc bị chặn kèm phần thiếu", "tools": ["order.create", "order.update", "handoff.transfer", "pricing.quote_order"],
     "writes": True},
    {"step": "clarify:<R#>", "tier": "main", "purpose": "hỏi / báo khách đúng điều đang chặn một yêu cầu rồi kết thúc lượt",
     "available": "chỉ khi yêu cầu thiếu thông tin / điều kiện chưa thỏa / bị cấm / executor đã từ chối", "output": "câu hỏi", "tools": [],
     "writes": False},
    {"step": "clarify", "tier": "main", "purpose": "hỏi khách nói lại khi câu mơ hồ rồi kết thúc lượt",
     "available": "chỉ khi có hold hoặc bộ hiểu báo needs_clarification", "output": "câu hỏi", "tools": [], "writes": False},
    {"step": "clarify_field:<trường>@<P#>", "tier": "main", "purpose": "bước 2 (18/11): hỏi khách ĐÚNG một thuộc tính biến thể còn thiếu "
                                                                     "(size …) khi giá / KM của mẫu phụ thuộc thuộc tính đó, rồi kết thúc lượt",
     "available": "chỉ khi B2_TWO_TIER và code (variant_gate, dữ liệu catalog + KM của BTC) xác định trường CÓ ảnh hưởng và CÒN thiếu cho "
                  "mẫu bị giữ giá / mẫu là đối tượng câu hỏi giá; mọi biến thể liên quan cùng giá-điều kiện thì không có bước này",
     "output": "câu hỏi + tác vụ báo giá đang chờ (s.pending_clarify); lượt sau khách trả lời → mở lại câu hỏi giá, báo đúng giá biến thể; "
               "đổi mẫu / từ chối → bỏ; giá trị không có → báo phần thiếu", "tools": [], "writes": False},
    {"step": "finish", "tier": "main", "purpose": "kết thúc lượt, trả lời bằng các khối đã có",
     "available": "luôn có; code chặn nếu còn câu hỏi / yêu cầu chưa phản hồi", "output": "câu trả lời", "tools": [], "writes": False},
    # ---------------------------------------------------------------- tầng outer (planner_b2tt.tasks)
    {"step": "consult_cheapest@<nhóm> | consult_most_expensive@<nhóm>", "tier": "outer", "purpose": "tìm mẫu rẻ / đắt nhất còn bán trong nhóm",
     "available": "khi bộ hiểu ghi tiêu chí sort và biết nhóm hàng", "output": "tác vụ cho tầng inner", "tools": [], "writes": False},
    {"step": "consult_named@<P#[,P#]>", "tier": "outer", "purpose": "xử lý ĐÚNG một / hai mẫu khách nêu (hoặc mẫu đang bàn khi khách hỏi "
                                                                     "đúng về nó): giá, KM, kho, hợp ngân sách / nhu cầu, so hai mẫu",
     "available": "b2tt-2: khách nêu 1–2 mẫu (parser catalog) và hỏi về sản phẩm, không xin mẫu khác",
     "output": "chuyển sang luồng main với phạm vi ref (main chỉ còn read_quote / read_stock các ref này); không survey, không gợi ý mẫu khác",
     "tools": [], "writes": False},
    {"step": "consult_alternative@<nhóm>", "tier": "outer", "purpose": "tìm mẫu KHÁC mẫu khách đang xem trong cùng nhóm (mẫu đó là mốc)",
     "available": "b2tt-2: bộ hiểu ghi goal find_other và có mốc (mẫu khách nêu hoặc đang bàn)",
     "output": "tác vụ cho tầng inner; xếp hạng loại mốc; đề xuất KHÔNG thay mẫu khách đang xem", "tools": [], "writes": False},
    {"step": "consult_recommend@<nhóm>", "tier": "outer", "purpose": "tư vấn mẫu trong nhóm theo nhu cầu đã biết",
     "available": "khi khách nhờ tư vấn / tìm trong nhóm, hoặc hỏi giá / KM / kho mà chưa có mẫu cụ thể (không mở khi khách đã nêu mẫu)",
     "output": "tác vụ cho tầng inner", "tools": [], "writes": False},
    {"step": "consult_clarify_category", "tier": "outer", "purpose": "hỏi khách nhóm hàng", "available": "khi chưa rõ nhóm hàng",
     "output": "tác vụ hỏi", "tools": [], "writes": False},
    {"step": "delegate_main_flow", "tier": "outer", "purpose": "chuyển lượt về luồng chính: planner B2 chính xử lý tiếp NGAY trong lượt "
                                                                "(đọc theo ref, chính sách, đơn, giỏ, đặt hàng)",
     "available": "luôn có. Code tự delegate (không hỏi Jev) ở lượt giao dịch / hỗn hợp / không có tác vụ tư vấn. Code chỉ bỏ lời gọi Jev "
                  "khi còn đúng một phương án hợp lệ về nghĩa: consult_named (cùng luồng main), rẻ / đắt nhất (main không so cực trị), "
                  "hỏi nhóm hàng; recommend / alternative thì Jev chọn giữa tác vụ đó và delegate", "output": "luồng main",
     "tools": [], "writes": False},
    # ---------------------------------------------------------------- tầng inner (planner_b2tt.inner_options)
    {"step": "survey:<nhóm>", "tier": "inner", "purpose": "đọc danh mục nhóm + tồn kho + giá mẫu còn hàng", "available": "khi chưa survey",
     "output": "dữ liệu để code so sánh", "tools": ["catalog.search", "inventory.check", "pricing.get_quote"], "writes": False},
    {"step": "answer", "tier": "inner", "purpose": "trả lời từ dữ liệu đã survey (code so sánh, chỉ nói điều có nguồn)",
     "available": "sau survey", "output": "khối product_pick", "tools": [], "writes": False},
    {"step": "ask_customer_need", "tier": "inner", "purpose": "hỏi một nhu cầu còn thiếu (trẻ nhỏ / ngân sách) rồi kết thúc lượt",
     "available": "chỉ tác vụ recommend / alternative khi chưa biết nhu cầu nào và chưa hỏi", "output": "câu hỏi", "tools": [],
     "writes": False},
    {"step": "ask_customer_category", "tier": "inner", "purpose": "hỏi nhóm hàng / mẫu rồi kết thúc lượt",
     "available": "chỉ tác vụ consult_clarify_category", "output": "câu hỏi", "tools": [], "writes": False},
    {"step": "finish_unresolved", "tier": "inner", "purpose": "dừng tác vụ tư vấn",
     "available": "luôn có",
     "output": "nếu CHƯA survey → chuyển lượt về luồng chính (unresolved_delegated, luồng main xử lý tiếp trong cùng lượt); nếu đã "
               "survey → code trả lời giới hạn chính xác từ dữ liệu đã đọc. b2tt-2: mô tả Jev nhìn thấy nay nói đúng hành vi này "
               "(trước ui6 là 'báo khách giới hạn')",
     "tools": [], "writes": False},
]
LIMITS = [
    "Hướng dẫn không cấp quyền: mọi lệnh ghi (commit_request) do code kiểm quyền + bằng chứng; hướng dẫn không được yêu cầu bỏ qua kiểm.",
    "Giá, khuyến mãi, tồn kho, thời gian giao, chính sách chỉ được nói khi có kết quả tool / đoạn chính sách trong lượt; hướng dẫn không chứa "
    "con số, mã đơn, SĐT, SKU, mã kịch bản (store.validate chặn).",
    "Jev không có bước 'hỏi khách' tự do ở tầng main: chỉ answer_ask (tự hỏi khi chưa gắn sản phẩm), clarify:<R#>, clarify (khi mơ hồ).",
    "Câu chữ trả lời do code / renderer dựng từ khối dữ liệu; Jev chỉ chọn bước. Hướng dẫn chỉ nên nói về việc chọn bước nào, khi nào.",
    "Không hỏi lại thông tin đã biết; không thay sản phẩm khách chọn khi khách chưa đồng ý.",
    "b2tt-2: đề xuất của tầng tư vấn không thay mẫu khách đã nêu; lời đặt không nêu mẫu ngay sau đề xuất khác mẫu đang bàn → main bỏ "
    "commit_request:R@P# (purchase_target_ambiguous), executor hỏi khách lấy mẫu nào.",
]


def _key(step):
    return re.split(r"[:@ ]", step, 1)[0]


def families():
    keys = []
    for f in FAMILIES:
        for part in f["step"].split(" | "):
            keys.append((_key(part), f["tier"]))
    return keys


def catalog():
    """→ {"families": [...], "limits": [...], "code_sha256": {tệp: sha}} — sha của đúng tệp nguồn đang nạp."""
    sha = {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest() for p in set(SOURCES.values())}
    return {"families": FAMILIES, "limits": LIMITS, "code_sha256": sha}


FUNCS = {"main": ("options", "_variant_field_options"), "outer": ("tasks",), "inner": ("inner_options",)}


def _body(src, fn):
    m = re.search(r"\ndef " + fn + r"\(.*?(?=\ndef |\Z)", src, re.S)
    return m.group(0) if m else ""


def _source_keys(body, var):
    """Khóa bước literal trong thân hàm dựng danh mục: desc["x..."] / out["x..."] / {"x...": ...} trả về trực tiếp.
    Khóa dạng f"consult_{crit['sort']}@..." → consult_<sort> theo SORT_TASKS."""
    keys = set()
    rets = re.findall(r'return \{"([a-z_]+)"', body) if var == "out" else []      # options() trả {"step": ...} — không phải bước
    for k in re.findall(var + r'\[f?"([a-z_]+)', body) + rets:
        keys.add(k)
    if "consult_{crit['sort']}" in body:
        keys.discard("consult_")
        keys |= {"consult_cheapest", "consult_most_expensive"}
    return keys


def check_source():
    """Họ bước trong FAMILIES ⇔ khóa bước literal trong thân options() / tasks() / inner_options() của đúng tệp đang nạp.
    → (thiếu_trong_code, thiếu_trong_danh_mục) — cả hai phải rỗng."""
    src = {t: open(p, encoding="utf-8").read() for t, p in SOURCES.items()}
    code = {t: _source_keys("".join(_body(src[t], fn) for fn in FUNCS[t]), "desc" if t == "main" else "out") for t in FUNCS}
    fam = {}
    for k, t in families():
        fam.setdefault(t, set()).add(k)
    missing_in_code = sorted((k, t) for t in fam for k in fam[t] if k not in code[t])
    missing_in_catalog = sorted((k, t) for t in code for k in code[t] if k not in fam.get(t, set()))
    return missing_in_code, missing_in_catalog
