#!/usr/bin/env python3
"""Validate a Yueke NonDegree open-format business handover ZIP.

This is not a disaster-restore verifier. It checks portability/integrity and
that authentication/session secret data is not exported as business rows.
"""
from __future__ import annotations
import argparse,json,hashlib,zipfile,re
from pathlib import Path,PurePosixPath

REQUIRED={
 'manifest.json','README.txt','database_structure.json','attachments_manifest.json',
 'data/organizations.csv','data/roles.csv','data/users.csv','data/periods.csv','data/settings.csv',
 'data/training_records.csv','data/qualifications.csv','data/rules.csv','data/point_entries.csv',
 'data/assessments.csv','data/organization_assessment_rules.csv','data/organization_assessments.csv',
 'data/organization_assessment_metric_evidence.csv','data/teacher_hr_profiles.csv',
 'data/training_projects.csv','data/training_courses.csv','data/training_classes.csv','data/teacher_participations.csv',
 'data/inbound_batches.csv','data/inbound_rows.csv','data/integration_schedules.csv','data/sync_items.csv','data/sync_call_logs.csv',
 'data/connections.csv','data/audit_events.csv',
 'delivery/initialization_configuration.json','delivery/database_dictionary.json','delivery/interface_data_catalog.json',
}
FORBIDDEN_DATA_BASENAMES={'auth_sessions.csv','login_throttles.csv','command_receipts.csv'}
FORBIDDEN_USER_HEADERS={'password_hash','auth_version','failures','locked_until','token_hash','csrf','storage_key','lease_token','lease_until'}
R6_TABLES={'record_revisions','calculation_batches','rule_trials','organization_rule_trials','disputes',
 'import_jobs','import_rows','tasks','task_attempts','notices','connection_checks','attachments'}

def sha(data):return hashlib.sha256(data).hexdigest()

def safe_name(name):
    p=PurePosixPath(name)
    return not p.is_absolute() and '..' not in p.parts and '\\' not in name and not name.startswith('/')

def verify(path):
    path=Path(path);errors=[];details={}
    try:
        with zipfile.ZipFile(path) as z:
            infos=z.infolist();names=[x.filename for x in infos]
            if len(names)!=len(set(names)):errors.append('ZIP存在重复路径')
            for info in infos:
                if not safe_name(info.filename):errors.append('ZIP路径不安全: '+info.filename)
                if (info.external_attr>>16)&0o170000==0o120000:errors.append('ZIP不允许符号链接: '+info.filename)
            if len(infos)>100000 or sum(x.file_size for x in infos)>1024**3 or any(x.file_size>512*1024**2 for x in infos):
                return {'status':'FAIL','errors':['移交包超过校验资源上限，必须分卷后按现场方案验证'],'disaster_restore_proven':False}
            missing=sorted(REQUIRED-set(names))
            if missing:errors.append('缺少必需文件: '+','.join(missing))
            if FORBIDDEN_DATA_BASENAMES & {PurePosixPath(x).name for x in names if x.startswith('data/')}:
                errors.append('业务移交包包含认证/会话数据表')
            if 'manifest.json' not in names:return {'status':'FAIL','errors':errors or ['manifest.json缺失']}
            manifest=json.loads(z.read('manifest.json'))
            version=manifest.get('format')
            if version not in {'Yueke NonDegree open handover v1','Yueke NonDegree open handover v2'}:errors.append('移交格式版本不匹配')
            entries=manifest.get('files') or [];seen=set()
            for item in entries:
                n=item.get('path');
                if not isinstance(n,str) or n in seen:errors.append('manifest文件项重复或无效');continue
                seen.add(n)
                if n not in names:errors.append('manifest引用缺失文件: '+n);continue
                data=z.read(n)
                if len(data)!=item.get('size'):errors.append('文件大小不匹配: '+n)
                if sha(data)!=item.get('sha256'):errors.append('文件SHA256不匹配: '+n)
            expected=set(names)-{'manifest.json'}
            if seen!=expected:
                errors.append('manifest文件集合不完整')
                details['manifest_missing']=sorted(expected-seen);details['manifest_extra']=sorted(seen-expected)
            import csv,io
            for csv_name in [n for n in names if n.startswith('data/') and n.endswith('.csv')]:
                raw=z.read(csv_name)
                if not raw:continue
                reader=csv.reader(io.StringIO(raw.decode('utf-8-sig')));headers=set(next(reader,[]))
                leaked=headers & FORBIDDEN_USER_HEADERS
                if leaked:errors.append(f'{csv_name}包含禁止移交的内部字段: '+','.join(sorted(leaked)))
            if 'data/connections.csv' in names:
                reader=csv.DictReader(io.StringIO(z.read('data/connections.csv').decode('utf-8-sig')))
                for row in reader:
                    try:cfg=json.loads(row.get('config') or '{}')
                    except json.JSONDecodeError:errors.append('connections.csv配置JSON无效');continue
                    bad=[k for k in cfg if re.search(r'(password|secret|token|api[_-]?key)',k,re.I) and k!='secret_env']
                    if bad:errors.append('connections.csv包含疑似接口密钥字段: '+','.join(sorted(bad)))
            if 'attachments_manifest.json' in names:
                rows=json.loads(z.read('attachments_manifest.json'))
                for item in rows:
                    arc=item.get('archive_path','')
                    if arc not in names:errors.append('附件清单引用文件缺失: '+str(arc));continue
                    data=z.read(arc)
                    if len(data)!=item.get('size') or sha(data)!=item.get('sha256'):errors.append('附件字节校验失败: '+str(item.get('id')))
            if version=='Yueke NonDegree open handover v2':
                verify_typed(z,manifest,errors,details)
            else:
                details['typed_roundtrip_verified']=False
                details['coverage_note']='旧v1包仅做旧格式完整性校验，不代表R6完整证据移交'
            details.update({'zip_files':len(names),'manifest_files':len(entries),'attachments':len(json.loads(z.read('attachments_manifest.json'))) if 'attachments_manifest.json' in names else 0})
    except (OSError,zipfile.BadZipFile,json.JSONDecodeError,UnicodeDecodeError,KeyError,TypeError,ValueError,AttributeError) as e:
        errors.append(type(e).__name__)
    return {'status':'PASS' if not errors else 'FAIL','errors':errors,'details':details,'kind':'OPEN_HANDOVER_PORTABILITY_CHECK','disaster_restore_proven':False}

def _csv_cell(value):
    if value is None:return ''
    if isinstance(value,(dict,list)):
        return json.dumps(value,ensure_ascii=False,separators=(',',':'))
    text=str(value)
    return "'"+text if isinstance(value,str) and text.lstrip(' \t\r\n').startswith(('=','+','-','@')) else text


def verify_typed(z,manifest,errors,details):
    """Check raw-value roundtrip, declared row counts and exported SQL foreign keys.

    SHA manifests detect accidental corruption, not forgery by a database owner.
    Credentials and installation attestations intentionally cannot be roundtripped.
    """
    import csv,io
    tables=manifest.get('tables')
    if not isinstance(tables,list):
        errors.append('v2缺少结构化表清单');return
    names=[t.get('name') for t in tables]
    expected={PurePosixPath(x).stem for x in REQUIRED if x.startswith('data/')}|R6_TABLES
    if len(names)!=len(set(names)) or not expected<=set(names):
        errors.append('v2表清单重复或缺少必需证据表')
    csv_members={n for n in z.namelist() if n.startswith('data/') and n.endswith('.csv')}
    json_members={n for n in z.namelist() if n.startswith('typed/') and n.endswith('.jsonl')}
    if csv_members!={t.get('csv_path') for t in tables} or json_members!={t.get('typed_path') for t in tables}:
        errors.append('v2实际数据文件与表清单不一致')
    by_model={};row_count=0
    for t in tables:
        name=t['name'];cols=t['columns'];keys=t['primary_key']
        if not cols or len(cols)!=len(set(cols)) or not set(keys)<=set(cols) or not keys:
            errors.append('表字段或主键声明无效: '+name);continue
        if FORBIDDEN_USER_HEADERS&set(cols):errors.append('JSONL包含禁止移交的内部字段: '+name)
        lines=z.read(t['typed_path']).decode('utf-8').splitlines()
        rows=[json.loads(line) for line in lines]
        if len(rows)!=t.get('rows'):errors.append('JSONL行数与清单不一致: '+name)
        pk=set()
        for row in rows:
            if not isinstance(row,dict) or set(row)!=set(cols):
                errors.append('JSONL字段集合不一致: '+name);continue
            key=tuple(row[k] for k in keys)
            if None in key or key in pk:errors.append('JSONL主键缺失或重复: '+name)
            pk.add(key)
        csv_rows=list(csv.reader(io.StringIO(z.read(t['csv_path']).decode('utf-8-sig'))))
        desired=[cols]+[[_csv_cell(row[c]) for c in cols] for row in rows]
        if csv_rows!=desired:errors.append('CSV显示值与JSONL精确值不一致: '+name)
        if t['model_table'] in by_model:errors.append('数据库表映射重复: '+name)
        by_model[t['model_table']]=(t,rows);row_count+=len(rows)
    structure=json.loads(z.read('database_structure.json'))
    lookup={}
    for model,(t,rows) in by_model.items():
        for c in t['columns']:
            if all(not isinstance(row[c],(list,dict)) for row in rows):
                lookup[(model,c)]={row[c] for row in rows}
    fk_checks=0
    for model,(t,rows) in by_model.items():
        if model not in structure:errors.append('数据库结构缺少移交表: '+model);continue
        for c in structure[model]['columns']:
            if c['name'] not in t['columns']:continue
            for ref in c.get('foreign_keys',[]):
                target,column=ref.rsplit('.',1)
                if target not in by_model:
                    errors.append('移交外键目标表遗漏: '+ref);continue
                values=lookup.get((target,column),set())
                if any(row[c['name']] is not None and row[c['name']] not in values for row in rows):
                    errors.append('移交存在悬空外键: '+model+'.'+c['name']+' -> '+ref)
                fk_checks+=1
    attachment_rows=by_model.get('attachments',({},[]))[1]
    attachments=json.loads(z.read('attachments_manifest.json'))
    metadata={row['id']:row for row in attachment_rows}
    if len(attachments)!=len(metadata) or {a['id'] for a in attachments}!=set(metadata):
        errors.append('附件清单与附件业务表不一致')
    for item in attachments:
        row=metadata.get(item['id'],{})
        for key in ('sha256','size','teacher_id','object_type','object_id','uploaded_by','mime'):
            if row.get(key)!=item.get(key):errors.append('附件证据关联不一致: '+str(item.get('id')));break
    details.update(typed_tables=len(tables),typed_rows=row_count,foreign_key_checks=fk_checks,
                   typed_roundtrip_verified=not errors,coverage_note='v2完整证据表、精确值、CSV显示与SQL外键校验；不是灾备恢复验收')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('zip');p.add_argument('--output');a=p.parse_args();r=verify(a.zip);payload=json.dumps(r,ensure_ascii=False,indent=2);print(payload)
    if a.output:Path(a.output).write_text(payload+'\n',encoding='utf-8')
    raise SystemExit(0 if r['status']=='PASS' else 2)
