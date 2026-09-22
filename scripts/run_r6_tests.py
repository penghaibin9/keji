#!/usr/bin/env python3
"""Repeatable synthetic regression in independently runnable groups.

Examples: python scripts/run_r6_tests.py --group r6_evidence
          python scripts/run_r6_tests.py --group installation
          python scripts/run_r6_tests.py --group all
Each group writes a separate log/XML, so a timed-out group need not restart all.
Does not access production systems or install dependencies.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
GROUPS={
 'p0_queries':['tests/p0/'+n+'.py' for n in ['test_read_queries','test_readiness','test_audit_and_middleware','test_https_smoke']],
 'p0_deployment':['tests/p0/test_deployment.py','tests/p0/test_preservation.py'],
 'installation':['tests/p0/test_r5_installation.py'],
 'r2_core':['tests/r2/'+n+'.py' for n in ['test_api','test_hardening','test_r3_authorization_matrix']],
 'r3_extension':['tests/r2/'+n+'.py' for n in ['test_r3_deploy_support','test_r3_excel','test_r3_handover_validator','test_r3_integrations','test_r3_org_assessment','test_r3_performance_acceptance','test_r3_release_gate','test_r3_route_security_audit','test_r3_settings','test_r3_workbenches']],
 'r4_r5':['tests/r2/'+n+'.py' for n in ['test_r4_dual_track','test_r4_inbound_schedule','test_r4_internal_closeout','test_r5_closeout']],
 'r6_evidence':['tests/r2/test_r6_evidence_chain.py'],
 'r6_portability':['tests/r2/test_r6_portability.py'],
}
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--group',choices=['all',*GROUPS],default='all');args=ap.parse_args()
    out=ROOT/'evidence/r6/retest';out.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PYTHONPATH':str(ROOT/'backend')+os.pathsep+os.environ.get('PYTHONPATH','')}
    names=GROUPS if args.group=='all' else [args.group];results=[]
    for name in names:
        print('Running',name,flush=True)
        with (out/(name+'.log')).open('w') as log:
            run=subprocess.run([sys.executable,'-m','pytest',*GROUPS[name],'-q','--tb=short','--junitxml='+str(out/(name+'.xml'))],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        results.append({'group':name,'exit_code':run.returncode,'log':str(out/(name+'.log'))})
        (out/'latest_group_results.json').write_text(json.dumps(results,indent=2))
        if run.returncode:return run.returncode
    if args.group=='all':
        with (out/'node.log').open('w') as log:
            run=subprocess.run(['node','--test',*[str(p) for p in sorted((ROOT/'tests/js').glob('*.test.mjs'))]],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if run.returncode:return run.returncode
    print('Synthetic groups completed; production gates are separate.');return 0
if __name__=='__main__':raise SystemExit(main())
