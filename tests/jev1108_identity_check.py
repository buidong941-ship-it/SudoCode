"""Integration fixture, not a benchmark: spoken phone cannot merge another profile."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tempfile.mkdtemp()) / 'identity.db')
os.environ['RAG_MODE'] = 'bm25'
from core.config import settings
from core.llm.generator import Generator
from core.llm.router import Router
from harness import agent, planner_decision
from harness.memory import Memory
from harness.tools import ToolBox
from harness.identity_permissions import may_bind_spoken_phone, may_forget

s = SimpleNamespace(phone='0912222999', customer={'customer_id': 'N-own', 'phone': '0912222999'}, channel_identity=None, proxy_caller=False)
assert may_bind_spoken_phone(s, '+84 912 222 999')
assert not may_bind_spoken_phone(s, '0984726714')
assert may_forget(s)
s.proxy_caller = True; assert not may_forget(s)
s = SimpleNamespace(phone=None, customer={'customer_id': 'C-own', 'phone': '0912222999'}, channel_identity='verified-transport-alias', proxy_caller=False)
assert may_bind_spoken_phone(s, '0912222999') and may_forget(s)

def exercise(allow_unverified):
    mem = Memory('identity-fixture-' + str(allow_unverified)); mem.wipe(); ToolBox.reset_world()
    session = agent.CallSession(memory=mem, today='2026-10-20', call_name='call_1', session_id='identity-fixture',
                                channel='hotline', channel_identity=None, phone='0912222999', input_mode='text',
                                router=Router('rules'), generator=Generator('offline'), config='full')
    session.start()
    decision = {'actions': ['order_status'], 'flags': {}, 'backend': 'fixture', 'simulated': True}
    with patch.object(planner_decision, 'decide', return_value=decision):
        if allow_unverified:
            with patch('harness.identity_permissions.may_bind_spoken_phone', return_value=True):
                row = session.turn('Tôi là Hoa, số điện thoại của tôi là 0984726714, tra đơn cho tôi.')
        else:
            row = session.turn('Tôi là Hoa, số điện thoại của tôi là 0984726714, tra đơn cho tôi.')
    queried = [tc for tc in row['tool_calls'] if tc['args'].get('phone') == '0984726714' or tc['args'].get('customer_phone') == '0984726714']
    return session, row, queried

with patch.multiple(settings, tool_transport='direct', planner_selector='jev', jev_simulated=True,
                    extractor_backend='rules', goal_contract=True, extractor_async=False, parallel_router=False):
    _, _, insecure_queries = exercise(True)
    current, row, protected_queries = exercise(False)
assert insecure_queries, 'fixture must demonstrate that bypassing the gate would query another profile'
assert not protected_queries, protected_queries
assert current.customer['customer_id'] != 'C001'
assert not any(w.get('customer_id') == 'C001' for w in row['memory_writes'])
print('identity integration OK: unverified spoken phone cannot query/merge/write another profile; no model APIs')
