"""Read source/runtime declarations without creating tables or sample accounts."""
from pathlib import Path
import sys,json,ast,hashlib,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
from app.main import create_app
app=create_app(Settings(env='test',database_url='sqlite://',secure_cookie=False,public_origin='http://testserver',allowed_hosts='testserver',storage_dir=Path('/tmp/nd-inventory-unused')))
routes=[{'path':r.path,'methods':sorted(r.methods),'module':r.endpoint.__module__,'function':r.endpoint.__name__}
        for r in app.routes if getattr(r,'methods',None)]
app.state.engine.dispose()
result={'kind':'DECLARATION_INVENTORY_NOT_ACCEPTANCE','api_route_count':sum(r['path'].startswith('/api/') for r in routes),
 'routes':routes,'unimplemented_contracts':[
  {'group':'Excel导入','paths':['GET /api/imports','GET /api/imports/templates/{kind}','POST /api/imports/{kind}/preview','GET /api/imports/{id}','GET /api/imports/{id}/errors','POST /api/imports/{id}/confirm']},
  {'group':'后台导出/下载/重试','paths':['POST /api/exports','GET /api/tasks/{id}/download','POST /api/tasks/{id}/retry']},
  {'group':'接口映射写入/真实适配','paths':['PUT /api/connections/{id}','POST /api/connections/validate','SSO/middle/province adapters']},
  {'group':'独立组织考核','paths':['organization-assessment model/migration/service/API/UI NOT IMPLEMENTED']}
 ]}
(ROOT/'evidence/r2/api-contract-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'api_route_count':result['api_route_count'],'total_declared_http_routes':len(routes)}))
