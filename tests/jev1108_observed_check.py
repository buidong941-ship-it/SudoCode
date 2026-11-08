"""Behavioral fixes: retain positive/negative claims; block unsupported promises."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.assertions import asserted_text, curative_problems
from harness import extractor, guardrails
from core.llm.generator import render_offline

assert not extractor.agent_claims('Về việc bảo hành 3 năm, em chưa có thông tin.')
assert not extractor.agent_claims('Em chưa có thông tin về bảo hành 3 năm đó ạ.')
claims = extractor.agent_claims('Giá máy 1.000.000đ, em chưa có thông tin về bảo hành 3 năm.')
assert any(c['field'] == 'price_vnd' and c['value'] == 1000000 for c in claims)
assert not any(c['field'] == 'warranty_months' for c in claims)
assert any(c['field'] == 'warranty_months' and c['value'] == 36 for c in extractor.agent_claims('Máy này bảo hành 3 năm.'))
assert any(c['field'] == 'promo_active' and c['value'] is False for c in extractor.agent_claims('Chương trình khuyến mãi đã hết hạn.'))
assert '1,2 triệu' in asserted_text('Giá máy 1,2 triệu, em chưa có thông tin bảo hành.')
assert curative_problems('Máy này được thiết kế để hỗ trợ điều trị hen suyễn cho trẻ em.')
assert curative_problems('Máy không chỉ chữa hen mà còn chữa viêm.')
assert not curative_problems('Em không thể xác nhận máy này chữa được hen suyễn.')
assert not curative_problems('Em xin chuyển sang nhân viên phụ trách.')
assert guardrails.promo_problems('Em đã ghi quà vào đơn.', {'active': [], 'expired': []})
assert not guardrails.promo_problems('Em không thể giữ quà khi chương trình đã hết.', {'active': [], 'expired': []})
assert not guardrails.promo_problems('Em giữ quà cho chị.', {'active': [{'type': 'gift'}], 'expired': []})
refusal = render_offline({'goals': ['refuse_internal'], 'facts': {}})
assert 'không thể cung cấp' in refusal and 'giá nhập' not in refusal.lower()
print('observed behavior checks OK; assertions retained, uncertainty excluded, unsupported promises blocked')
