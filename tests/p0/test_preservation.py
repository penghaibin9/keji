"""Diff-sensitive preservation checks; these do not prove business E2E."""
import ast,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BEFORE=ROOT/'tests/fixtures/p0_before'


def test_preservation_baseline_bytes_match_recorded_hashes():
    manifest=json.loads((BEFORE/'MANIFEST.json').read_text(encoding='utf-8'))
    assert {row['path'] for row in manifest['files']}=={'backend/app/models.py','backend/app/services.py','frontend/app.js'}
    for row in manifest['files']:
        raw=(BEFORE/row['path']).read_bytes()
        assert len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256']


def test_existing_models_preserved_except_authorized_security_columns():
    before=ast.parse((BEFORE/'backend/app/models.py').read_text(encoding='utf-8'))
    after=ast.parse((ROOT/'backend/app/models.py').read_text(encoding='utf-8'))
    additions={'User':{'authorization_pending'},'AuthSession':{'auth_method'}}
    for node in after.body:
        if isinstance(node,ast.ClassDef) and node.name in additions:
            added=[x for x in node.body if isinstance(x,ast.AnnAssign) and isinstance(x.target,ast.Name) and x.target.id in additions[node.name]]
            assert {x.target.id for x in added}==additions[node.name]
            node.body=[x for x in node.body if x not in added]
    assert ast.dump(before,include_attributes=False)==ast.dump(after,include_attributes=False)


def test_existing_scoring_and_ledger_business_functions_are_preserved():
    def functions(path):
        return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    before=functions(BEFORE/'backend/app/services.py');after=functions(ROOT/'backend/app/services.py')
    # R6 intentionally validates previously archived evidence before reusing its score.
    # Formula evaluation and all ledger/calculation mutations remain AST-identical.
    # 2026-09-26 procurement fixes intentionally changed three functions:
    #  - calculate_points: skip-unchanged now also requires same rule + unchanged sources (calculation freshness);
    #  - calculate_assessments: refuses when upstream point evidence is stale (require_current_sources);
    #  - insert_record: manual source is validated against the dictionary; import/middle channels force their source.
    # record_query/stats moved to read_queries.py.  The formula itself (evaluate) and the
    # remaining helpers stay AST-identical; the changed ones are pinned by their new checks below.
    changed_20260926={'calculate_points','calculate_assessments','insert_record'}
    untouched=set(before)-{'record_query','stats','facts'}-changed_20260926
    assert {'evaluate','active_rule','rounded','qualification_revision'}<=untouched
    assert set(before)-{'record_query','stats'}<=set(after)
    assert 'verified_archive' in after['facts'] and 'previous_frozen' in after['facts']
    assert "'source_changes'" in after['calculate_points'] and "'rule_id'" in after['calculate_points']
    assert "'require_current_sources'" in after['calculate_assessments'] and "'point_source_changes'" in after['calculate_assessments']
    assert "'validate_manual_source'" in after['insert_record']
    assert all(before[name]==after[name] for name in untouched)


def test_existing_frontend_function_entries_not_removed():
    pattern=r'(?m)(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\('
    before=set(re.findall(pattern,(BEFORE/'frontend/app.js').read_text(encoding='utf-8')))
    after=set(re.findall(pattern,(ROOT/'frontend/app.js').read_text(encoding='utf-8')))
    assert before<=after
