"""Procurement delivery artifacts available to school administrators."""
from urllib.parse import quote
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import Response
from ..core import current_actor,read_operation,audit
from ..delivery import configuration_snapshot,database_dictionary,delivery_workbook
router=APIRouter(prefix='/api',tags=['交付与初始化清单'])

@router.get('/delivery/configuration')
def configuration(request:Request):
    def load(db,a,s):a.require_admin();return {'configuration':configuration_snapshot(db),'database_dictionary':database_dictionary()}
    return read_operation(request,'data.export',load)

@router.get('/delivery/configuration.xlsx')
def configuration_xlsx(request:Request):
    with request.app.state.sessions.begin() as db:
        a,s=current_actor(db,request);a.require('data.export');a.require_admin();data=delivery_workbook(db)
        audit(db,a,'delivery','configuration','导出初始化配置与数据字典',after={'bytes':len(data)},reason='采购交付配置清单')
    name=quote('平台初始化配置与数据字典.xlsx')
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f"attachment; filename*=UTF-8''{name}",'X-Content-Type-Options':'nosniff'})
