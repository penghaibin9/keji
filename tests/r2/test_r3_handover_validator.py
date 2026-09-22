import importlib.util,sys
from pathlib import Path
from app.worker import run_once
from conftest import auth,post
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('verify_handover',ROOT/'scripts/verify_handover.py');mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

def test_generated_handover_passes_portability_validator(client2,app2,tmp_path):
    auth(client2,'schooladmin')
    r=post(client2,'/api/exports',{'kind':'handover','filters':{},'confirmed':True});assert r.status_code==200,r.text
    task=r.json();assert run_once(app2.state.settings)['status']=='DONE'
    d=client2.get(f"/api/tasks/{task['id']}/download");assert d.status_code==200
    path=tmp_path/'handover.zip';path.write_bytes(d.content)
    result=mod.verify(path)
    assert result['status']=='PASS',result
    assert result['disaster_restore_proven'] is False
    assert result['details']['zip_files']>=15
