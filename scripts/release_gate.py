#!/usr/bin/env python3
"""Aggregate production release evidence for the procurement PDF.

It deliberately refuses to infer PASS from missing evidence. Construction tests
are useful but cannot substitute MySQL/browser/performance/school samples or
external-interface acceptance.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from check_assembly import inspect_assembly

EVIDENCE_KEYS={
 'mysql':'MySQL 8.4 canonical fresh/repeat/restore + legacy rejection evidence',
 'browser':'native browser four-role E2E evidence',
 'performance':'PDF 13.7/13.8 performance evidence',
 'school_sample':'school real sample dual-track 100% evidence',
 'external':'SSO/data-hub/province external integration evidence',
}

def read_json(path):
    if not path:return None
    p=Path(path)
    if not p.is_file():return None
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError,UnicodeDecodeError):return {'_invalid':True}

def evidence_pass(kind,obj):
    if not isinstance(obj,dict) or obj.get('_invalid'):return False
    if kind=='performance':return obj.get('overall_pass') is True and obj.get('tls_verified') is True
    if kind=='external':
        states=obj.get('connections') or {}
        return all(states.get(x)== 'PASS' for x in ('school_sso','school_data_hub','province_platform'))
    if kind=='school_sample':return obj.get('points_match_rate')==1 and obj.get('assessment_match_rate')==1 and obj.get('signed_off') is True
    if kind=='mysql':
        return (obj.get('evidence_kind') == 'REAL_MYSQL_8_4'
          and obj.get('database_engine') == 'mysql'
          and str(obj.get('mysql_version','')).startswith('8.4.')
          and 'mariadb' not in str(obj.get('mysql_version','')).lower()
          and obj.get('synthetic') is False
          and obj.get('installation_scope') == 'fresh_school_only'
          and obj.get('baseline_revision') == '20260918_0001'
          and all(obj.get(x) is True for x in ('fresh_migration','canonical_repeat_noop','canonical_restore_drill',
              'schema_checks','legacy_upgrade_rejected','legacy_restore_rejected','stamp_only_rejected','provenance_checked')))
    if kind=='browser':return obj.get('four_roles') is True and obj.get('native_browser') is True and obj.get('critical_flows_pass') is True and obj.get('security_negative_pass') is True
    return False

def run(root,paths):
    assembly=inspect_assembly(root);checks=[]
    checks.append({'key':'source_assembly','name':'source + Alembic graph','pass':assembly['status']=='PASS','detail':assembly})
    for key,name in EVIDENCE_KEYS.items():
        obj=read_json(paths.get(key));ok=evidence_pass(key,obj)
        checks.append({'key':key,'name':name,'pass':ok,'evidence':obj if obj is not None else 'MISSING'})
    blockers=[x['key'] for x in checks if not x['pass']]
    return {'status':'PASS' if not blockers else 'BLOCKED','deployment_allowed':not blockers,'blockers':blockers,'checks':checks,
            'note':'PASS means evidence set is complete for this gate; procurement sign-off and service obligations remain human/contractual.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));ap.add_argument('--output')
    for k in EVIDENCE_KEYS:ap.add_argument('--'+k.replace('_','-'),dest=k)
    a=ap.parse_args();paths={k:getattr(a,k) for k in EVIDENCE_KEYS};r=run(Path(a.root),paths);payload=json.dumps(r,ensure_ascii=False,indent=2)
    if a.output:Path(a.output).write_text(payload+'\n',encoding='utf-8')
    print(payload);raise SystemExit(0 if r['status']=='PASS' else 2)
