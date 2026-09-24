from pathlib import Path
from io import BytesIO
from openpyxl import load_workbook
from app.settings_catalog import STATUS_LABEL_DEFAULTS
from app.excel_io import template_bytes
from conftest import auth,post,put


def _settings(client):
    r=client.get('/api/settings');assert r.status_code==200,r.text
    return {x['key']:x for x in r.json()['items']}


def test_dictionary_is_visible_to_portal_and_only_known_state_codes_are_configurable(client2):
    auth(client2,'teacher')
    r=client2.get('/api/dictionaries');assert r.status_code==200,r.text
    data=r.json();assert data['import_max_rows']==5000
    assert data['status_labels']['ARCHIVED']=='已归档'
    assert '经核对人工录入' in data['record_sources']
    auth(client2,'schooladmin');settings=_settings(client2);obj=settings['business_dictionary']
    bad={**obj['value'],'status_labels':{**obj['value']['status_labels'],'INVENTED':'伪状态'}}
    r=put(client2,'/api/settings/business_dictionary',{'value':bad,'reason':'反向验证未知状态码','basis':'采购配置安全','expected_version':obj['version']})
    assert r.status_code==422,r.text


def test_business_dictionary_controls_record_source_and_notice_category(client2):
    auth(client2,'schooladmin');settings=_settings(client2);obj=settings['business_dictionary']
    value={**obj['value'],'record_sources':['学校登记'],'notice_categories':['校内通知']}
    r=put(client2,'/api/settings/business_dictionary',{'value':value,'reason':'学校字典调整','basis':'采购初始化配置','expected_version':obj['version']});assert r.status_code==200,r.text
    d=client2.get('/api/dictionaries').json();assert d['record_sources']==['学校登记'] and d['notice_categories']==['校内通知']
    payload={'external_key':'DICT-R1','teacher_id':'teacher','event_date':'2026-09-08','project_code':'PX','project':'项目X','course_code':'CX','course':'课程X','class_code':'CLX','class_name':'班级X','hours':'2','participants':5,'income':'100','source':'经核对人工录入','reason':'字典反向测试','basis':'测试'}
    r=post(client2,'/api/records',payload);assert r.status_code==422,r.text
    payload['source']='学校登记';r=post(client2,'/api/records',payload);assert r.status_code==200,r.text
    notice={'title':'测试通知','category':'业务通知','org_id':'school','body':'测试正文','published':True,'reason':'字典反向测试','basis':'测试'}
    r=post(client2,'/api/notices',notice);assert r.status_code==422,r.text
    notice['category']='校内通知';r=post(client2,'/api/notices',notice);assert r.status_code==200,r.text


def test_configurable_excel_row_limit_is_enforced_before_business_write(client2):
    auth(client2,'schooladmin');settings=_settings(client2);obj=settings['import_policy']
    r=put(client2,'/api/settings/import_policy',{'value':{'max_rows':100},'reason':'调整单批导入上限','basis':'采购要求行数可配置','expected_version':obj['version']});assert r.status_code==200,r.text
    assert client2.get('/api/dictionaries').json()['import_max_rows']==100
    wb=load_workbook(BytesIO(template_bytes('records')));ws=wb.active
    for i in range(101):
        ws.append([f'LIMIT-{i:03d}','J001','2026-09-01','P1','项目','C1','课程','CL1','班级',1,1,1,'Excel导入'])
    out=BytesIO();wb.save(out);wb.close()
    before=client2.get('/api/records?size=1').json()['total']
    r=client2.post('/api/imports/records/preview',files={'file':('records.xlsx',out.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert r.status_code==422,r.text
    assert '100' in r.json()['detail']
    assert client2.get('/api/records?size=1').json()['total']==before


def test_import_policy_range_and_status_labels_have_fail_closed_validation(client2):
    auth(client2,'schooladmin');settings=_settings(client2)
    p=settings['import_policy'];r=put(client2,'/api/settings/import_policy',{'value':{'max_rows':99},'reason':'反向测试','basis':'边界','expected_version':p['version']});assert r.status_code==422
    d=settings['business_dictionary'];labels=dict(STATUS_LABEL_DEFAULTS);labels.pop('ARCHIVED')
    value={**d['value'],'status_labels':labels}
    r=put(client2,'/api/settings/business_dictionary',{'value':value,'reason':'反向测试','basis':'不能删除合法状态码','expected_version':d['version']});assert r.status_code==422


def test_setting_history_is_directly_readable_from_configuration_page(client2):
    auth(client2,'schooladmin'); settings=_settings(client2); brand=settings['branding']
    r=put(client2,'/api/settings/branding',{'value':{'school_name':'历史测试学校'},'reason':'验证配置历史','basis':'PDF 3.5','expected_version':brand['version']})
    assert r.status_code==200,r.text
    hist=client2.get('/api/settings/branding/history');assert hist.status_code==200,hist.text
    row=hist.json()['items'][0]
    assert row['actor_name']=='学校测试管理员'
    assert row['reason']=='验证配置历史'
    assert row['before']['value']['school_name']=='隔离测试学校'
    assert row['after']['value']['school_name']=='历史测试学校'
    js=(Path(__file__).resolve().parents[2]/'frontend/app.js').read_text(encoding='utf-8')
    assert "setting-history" in js and "async function settingHistory" in js
