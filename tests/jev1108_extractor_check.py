"""Independent extraction routes and preparation without cart writes; Kaggle only."""
import sys
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import settings
from harness import extractor, llm_extract, jev_hybrid, planner_table
from harness.question_classifiers import jev_slots
from jev1108_check import main as contracts

with patch.multiple(settings, extractor_backend='hybrid', extractor_confidence_gate=False,
                    extractor_jev_hybrid=True, extractor_no_jev=True):
    with patch.object(jev_hybrid, 'customer') as forbidden, patch.object(llm_extract, 'customer_slots', return_value={'address': '15 Trần Phú'}):
        assert extractor.customer_slots('Giao về 15 Trần Phú nhé.', '2026-10-20')['address'] == '15 Trần Phú'
        forbidden.assert_not_called()
    claim = {'field': 'price_vnd', 'value': 1000000, 'text': 'Giá máy 1.000.000đ ạ.'}
    with patch.object(jev_hybrid, 'claims') as forbidden, patch.object(llm_extract, 'agent', return_value=([], [claim])), patch.object(jev_slots, 'classify_agent_questions', return_value=[]) as questions:
        _, claims = extractor.analyze_agent(claim['text'], {}, meta={})
        forbidden.assert_not_called(); questions.assert_called_once()
        assert any(c['field'] == 'price_vnd' and c['value'] == 1000000 for c in claims)
    with patch.object(settings, 'extractor_confidence_gate', True), patch('harness.rule_confidence.question', return_value={'certified': True, 'checks': {}, 'reason': 'fixture'}), patch.object(llm_extract, 'agent', return_value=([], [claim])) as claim_llm, patch.object(jev_slots, 'classify_agent_questions') as question_llm:
        _, claims = extractor.analyze_agent(claim['text'], {}, meta={})
        claim_llm.assert_called_once()
        question_llm.assert_not_called()
        assert claims == [claim]
print('independent customer/claim/question routes OK; question certificate does not suppress claim extraction')
