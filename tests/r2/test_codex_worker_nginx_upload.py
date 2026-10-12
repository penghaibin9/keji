"""Deployment regression checks using isolated SQLite and synthetic attachments."""
import io,logging,re,uuid,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from sqlalchemy import event,text
from sqlalchemy.exc import SQLAlchemyError
from app import installation,worker
from app.config import Settings
from app.models import RuntimeState
from app.routes.files import inspect_upload
from conftest import auth
from test_api import qual,make_assessment

MIMES={'.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
       '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}


def office_bytes(ext,extra=(),omit=()):
    part='word/document.xml' if ext=='.docx' else 'xl/workbook.xml'
    content=b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic evidence</w:t></w:r></w:p></w:body></w:document>' if ext=='.docx' else b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Evidence" sheetId="1" r:id="rId1"/></sheets></workbook>'
    types=f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/{part}" ContentType="{MIMES[ext]}.main+xml"/>'
    if ext=='.xlsx':types+='<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    entries=[('[Content_Types].xml',types+'</Types>'),(part,content),('_rels/.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{part}"/></Relationships>')]
    if ext=='.xlsx':entries.extend([('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'),('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')])
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        for name,data in [*entries,*extra]:
            if name not in omit:archive.writestr(name,data)
    return out.getvalue()


def revision_table(engine,heads):
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
        for head in heads:connection.execute(text('INSERT INTO alembic_version VALUES (:head)'),{'head':head})


def test_worker_main_reuses_resources_and_checks_revision_each_round(app2,monkeypatch):
    engine=app2.state.engine;cfg=app2.state.settings.model_copy(update={'env':'production'})
    revision_table(engine,[installation.CURRENT_REVISION])
    ticks=iter([2,599,600,602]);clock=[0];full_checks=[];queries=[]
    def sleep(seconds):
        assert seconds==2
        try:clock[0]=next(ticks)
        except StopIteration:raise KeyboardInterrupt
    def canonical(connection,*,require_mysql):
        assert connection.engine is engine and require_mysql is True
        full_checks.append(clock[0])
    def query(connection,cursor,statement,parameters,context,many):queries.append(statement)
    event.listen(engine,'before_cursor_execute',query)
    factory=Mock(return_value=engine);sessions=Mock(wraps=worker.sessionmaker);dispose=Mock(wraps=engine.dispose)
    monkeypatch.setattr(worker,'Settings',lambda:cfg);monkeypatch.setattr(worker,'make_engine',factory)
    monkeypatch.setattr(worker,'sessionmaker',sessions);monkeypatch.setattr(engine,'dispose',dispose)
    monkeypatch.setattr(worker,'time',SimpleNamespace(monotonic=lambda:clock[0],sleep=sleep))
    monkeypatch.setattr(installation,'require_canonical',canonical)
    try:
        with pytest.raises(KeyboardInterrupt):worker.main()
    finally:event.remove(engine,'before_cursor_execute',query)
    assert factory.call_count==sessions.call_count==dispose.call_count==1
    assert full_checks==[0,600]
    assert queries.count('SELECT version_num FROM alembic_version')==5
    with app2.state.sessions() as db:assert db.get(RuntimeState,'worker').value['healthy'] is True


@pytest.mark.parametrize('heads',[None,[],['old'],[installation.CURRENT_REVISION,'other'],[installation.CURRENT_REVISION]*2])
def test_worker_light_check_failure_does_not_claim_or_refresh_heartbeat(app2,monkeypatch,heads):
    if heads is not None:revision_table(app2.state.engine,heads)
    cfg=app2.state.settings.model_copy(update={'env':'production'})
    calls={name:Mock() for name in ('heartbeat','enqueue_due_schedules','claim_task')}
    for name,mock in calls.items():monkeypatch.setattr(worker,name,mock)
    canonical=Mock();dispose=Mock();monkeypatch.setattr(installation,'require_canonical',canonical)
    monkeypatch.setattr(app2.state.engine,'dispose',dispose)
    error=SQLAlchemyError if heads is None else installation.InstallationRejected
    with pytest.raises(error):worker.run_once(cfg,engine=app2.state.engine,sessions=app2.state.sessions,check_schema=False)
    for mock in [*calls.values(),canonical,dispose]:mock.assert_not_called()


def test_worker_full_check_failure_blocks_tasks_and_can_recover(app2,monkeypatch):
    cfg=app2.state.settings.model_copy(update={'env':'production'});clock=[0]
    revision_table(app2.state.engine,[installation.CURRENT_REVISION])
    canonical=Mock(side_effect=[installation.InstallationRejected('SYNTHETIC_FAILURE'),None])
    heartbeat=Mock(wraps=worker.heartbeat)
    def sleep(seconds):
        if clock[0]==0:
            heartbeat.assert_not_called();clock[0]=2
        else:raise KeyboardInterrupt
    monkeypatch.setattr(worker,'Settings',lambda:cfg);monkeypatch.setattr(worker,'make_engine',lambda _:app2.state.engine)
    monkeypatch.setattr(worker,'time',SimpleNamespace(monotonic=lambda:clock[0],sleep=sleep))
    monkeypatch.setattr(installation,'require_canonical',canonical);monkeypatch.setattr(worker,'heartbeat',heartbeat)
    with pytest.raises(KeyboardInterrupt):worker.main()
    assert canonical.call_count==2 and heartbeat.call_count==1


def test_worker_no_argument_call_owns_and_disposes_engine(app2,monkeypatch):
    factory=Mock(return_value=app2.state.engine);dispose=Mock(wraps=app2.state.engine.dispose)
    monkeypatch.setattr(worker,'Settings',lambda:app2.state.settings)
    monkeypatch.setattr(worker,'make_engine',factory);monkeypatch.setattr(app2.state.engine,'dispose',dispose)
    assert worker.run_once()=={'status':'IDLE','claimed':False}
    factory.assert_called_once_with(app2.state.settings.database_url);dispose.assert_called_once_with()


def test_nginx_access_format_omits_queries_and_referrer():
    config=(Path(__file__).resolve().parents[2]/'deploy/nginx.conf').read_text(encoding='utf-8')
    formats=re.findall(r'log_format\s+(\w+)\s+([^;]+);',config)
    assert formats
    for name,body in formats:
        variables=set(re.findall(r'\$\w+',body))
        assert not variables&{'$request','$args','$request_uri','$http_referer'}
        assert {'$uri','$request_method','$server_protocol','$status','$body_bytes_sent','$request_time'}<=variables
    assert re.search(r'access_log\s+/dev/stdout\s+nd_noquery\s*;',config)


def test_settings_disable_default_uvicorn_access_log(monkeypatch):
    logger=logging.getLogger('uvicorn.access');output=io.StringIO()
    monkeypatch.setattr(logger,'disabled',False);monkeypatch.setattr(logger,'handlers',[logging.StreamHandler(output)])
    monkeypatch.setattr(logger,'level',logging.INFO);monkeypatch.setattr(logger,'propagate',False)
    cfg=Settings(env='test',database_url='sqlite://',secure_cookie=False,public_origin='http://testserver')
    assert cfg.upload_limit_mb==10 and logger.disabled
    logger.info('%s - "%s %s HTTP/%s" %d','127.0.0.1','GET','/api/auth/sso/callback?ticket=synthetic-secret','1.1',200)
    assert output.getvalue()==''


@pytest.mark.parametrize('ext',MIMES)
def test_office_content_type(ext):
    assert inspect_upload('证明'+ext.upper(),office_bytes(ext))==MIMES[ext]


@pytest.mark.parametrize('ext',MIMES)
@pytest.mark.parametrize('macro',['word/vbaProject.bin','xl/VBAPROJECT.BIN','vbaProject.bin'])
def test_office_macro_rejected(ext,macro):
    with pytest.raises(HTTPException) as exc:inspect_upload('证明'+ext,office_bytes(ext,[(macro,b'macro')]))
    assert exc.value.status_code==422


@pytest.mark.parametrize('ext',MIMES)
@pytest.mark.parametrize('invalid',['not_zip','missing_types','missing_part','wrong_kind','broken_crc'])
def test_office_fake_or_damaged_file_rejected(ext,invalid):
    part='word/document.xml' if ext=='.docx' else 'xl/workbook.xml'
    if invalid=='not_zip':data=b'not an office archive'
    elif invalid=='missing_types':data=office_bytes(ext,omit=['[Content_Types].xml'])
    elif invalid=='missing_part':data=office_bytes(ext,omit=[part])
    elif invalid=='wrong_kind':data=office_bytes('.xlsx' if ext=='.docx' else '.docx')
    else:data=office_bytes(ext,extra=[('evidence.txt',b'crc-original')]).replace(b'crc-original',b'crc-modified')
    with pytest.raises(HTTPException) as exc:inspect_upload('证明'+ext,data)
    assert exc.value.status_code==422


@pytest.mark.parametrize('ext',MIMES)
@pytest.mark.parametrize('limit',['entries','uncompressed'])
def test_office_zip_bomb_rejected_before_decompression(ext,limit,monkeypatch):
    out=io.BytesIO(office_bytes(ext))
    with zipfile.ZipFile(out,'a',compression=zipfile.ZIP_DEFLATED) as archive:
        if limit=='entries':
            for i in range(2001-len(archive.infolist())):archive.writestr(f'extra/{i}',b'')
        else:
            with archive.open('huge.bin','w') as entry:
                for _ in range(201):entry.write(b'0'*(1024*1024))
    assert len(out.getvalue())<10*1024*1024
    checksum=Mock();monkeypatch.setattr(zipfile.ZipFile,'testzip',checksum)
    with pytest.raises(HTTPException) as exc:inspect_upload('证明'+ext,out.getvalue())
    assert exc.value.status_code==422;checksum.assert_not_called()


@pytest.mark.parametrize('ext',['.heic','.docm','.xlsm','.exe','.doc','.xls'])
def test_unsupported_formats_remain_rejected_with_iphone_guidance(ext):
    with pytest.raises(HTTPException) as exc:inspect_upload('证明'+ext,office_bytes('.docx'))
    assert exc.value.status_code==422
    assert '兼容性最佳' in exc.value.detail and '截图后上传' in exc.value.detail


@pytest.mark.parametrize('kind',['qualification','assessment'])
@pytest.mark.parametrize('ext',MIMES)
def test_office_upload_and_both_download_paths_force_attachment(client2,kind,ext):
    if kind=='assessment':obj=make_assessment(client2);auth(client2,'teacher')
    else:auth(client2,'teacher');obj=qual(client2)
    data=office_bytes(ext)
    response=client2.post(f'/api/attachments/{kind}/{obj["id"]}',files={'file':('证明'+ext,data,'application/octet-stream')},
        data={'reason':'隔离文档上传核验','expected_version':obj['version']},headers={'Idempotency-Key':str(uuid.uuid4())})
    assert response.status_code==200,response.text
    item=response.json();assert item['mime']==MIMES[ext]
    response=client2.get('/api/attachments/'+item['id']+'/download')
    assert response.status_code==200 and response.content==data
    assert response.headers['content-type']==MIMES[ext]
    assert response.headers['content-disposition'].startswith('attachment;')
    assert response.headers['x-content-type-options']=='nosniff'
    auth(client2,'otherteacher')
    assert client2.get('/api/attachments/'+item['id']+'/download').status_code==403
