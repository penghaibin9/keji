"""Diff-sensitive preservation checks; these do not prove business E2E."""
import ast,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def test_existing_models_are_byte_for_byte_preserved():
    assert (ROOT/'backend/app/models.py').read_bytes()==(ROOT/'evidence/before/backend/app/models.py').read_bytes()


def test_existing_scoring_and_ledger_business_functions_are_preserved():
    def functions(path):
        return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(path.read_text()).body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    before=functions(ROOT/'evidence/before/backend/app/services.py');after=functions(ROOT/'backend/app/services.py')
    # R6 intentionally validates previously archived evidence before reusing its score.
    # Formula evaluation and all ledger/calculation mutations remain AST-identical.
    untouched=set(before)-{'record_query','stats','facts'}
    assert {'evaluate','calculate_points','calculate_assessments'}<=untouched
    assert 'verified_archive' in after['facts'] and 'previous_frozen' in after['facts']
    assert all(before[name]==after[name] for name in untouched)


def test_existing_frontend_function_entries_not_removed():
    pattern=r'(?m)(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\('
    before=set(re.findall(pattern,(ROOT/'evidence/before/frontend/app.js').read_text()))
    after=set(re.findall(pattern,(ROOT/'frontend/app.js').read_text()))
    assert before<=after
