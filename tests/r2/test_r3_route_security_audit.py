import importlib.util,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('route_security_audit',ROOT/'scripts/route_security_audit.py')
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

def test_all_api_routes_have_canonical_auth_primitive_except_explicit_auth_bootstrap():
    result=mod.audit(ROOT)
    assert result['status']=='PASS',result['violations']
    assert result['route_count']>=90
    assert result['public_routes']==[
        'GET /api/auth/sso/callback',
        'GET /api/auth/sso/implementation-callback',
        'GET /api/auth/sso/start',
        'GET /api/auth/sso/status',
        'POST /api/auth/login',
    ]
    assert not result['violations']
