import importlib.util,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('release_gate',ROOT/'scripts/release_gate.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

def test_fresh_source_passes_but_release_remains_blocked_without_field_evidence(tmp_path):
    r=m.run(ROOT,{})
    assert r['status']=='BLOCKED' and not r['deployment_allowed']
    assert 'source_assembly' not in r['blockers']
    assert {'mysql','browser','performance','school_sample','external'} <= set(r['blockers'])

def test_evidence_parsers_do_not_accept_partial_or_lab_results():
    assert not m.evidence_pass('performance',{'overall_pass':True,'tls_verified':False})
    assert not m.evidence_pass('mysql',{'fresh_migration':True})
    assert not m.evidence_pass('browser',{'native_browser':True})
    assert not m.evidence_pass('external',{'connections':{'school_sso':'PASS'}})
    assert not m.evidence_pass('school_sample',{'points_match_rate':1,'assessment_match_rate':1,'signed_off':False})
