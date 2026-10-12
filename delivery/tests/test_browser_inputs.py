"""Input gates only, NOT browser/E2E success proofs."""
import json
import pytest
from delivery.browser_acceptance import validated_inputs
from delivery.common import Blocked

@pytest.fixture
def inputs(tmp_path):
    p=tmp_path/'mysql.json';d=tmp_path/'data.json';c=tmp_path/'accounts.json'
    p.write_text(json.dumps({'version':'8.4.0','real_mysql_installation':True,'provenance':{'baseline_revision':'20260918_0001','source_kind':'canonical_empty_school','installation_id':'input-validation-test-only'}}))
    d.write_text(json.dumps({'installation_id':'input-validation-test-only'}))
    c.write_text(json.dumps({r:{'username':'synthetic-'+r,'password':'InputOnly_NotALivePassword_20'} for r in ('school','teacher','teacher2','dept','college')}))
    return c,d,p

@pytest.mark.parametrize('origin',['http://127.0.0.1:18443','https://example.com:18443','https://127.0.0.1:443','https://name:secret@127.0.0.1:18443'])
def test_rejects_non_local_or_insecure_browser_targets(inputs,origin):
    with pytest.raises(Blocked):validated_inputs(origin,*inputs)

def test_rejects_missing_real_mysql_receipt(inputs):
    c,d,p=inputs;j=json.loads(p.read_text());j['real_mysql_installation']=False;p.write_text(json.dumps(j))
    with pytest.raises(Blocked,match='REAL_MYSQL'):validated_inputs('https://127.0.0.1:18443',c,d,p)

def test_rejects_data_from_different_installation(inputs):
    c,d,p=inputs;d.write_text(json.dumps({'installation_id':'wrong-installation'}))
    with pytest.raises(Blocked,match='IDENTITY_MISMATCH'):validated_inputs('https://127.0.0.1:18443',c,d,p)

def test_report_writer_works_without_unix_fchmod(tmp_path,monkeypatch):
    import os
    from delivery.common import secure_json
    monkeypatch.delattr(os,'fchmod',raising=False)
    target=tmp_path/'browser-report.json'
    secure_json(target,{'status':'BLOCKED','normal_browser_business':False})
    assert json.loads(target.read_text())['status']=='BLOCKED'
