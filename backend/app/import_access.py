"""Import staging is sensitive business data, not a perpetual uploader entitlement.

Proofs record original access context; they never grant authority. Every access
also checks today's permissions and referenced people/organizations. No inferred
proof is written for legacy jobs. This is consistency protection, not a signature
against an administrator who controls the whole database.
"""
from __future__ import annotations
from copy import deepcopy
from fastapi import HTTPException
from sqlalchemy import select
from .core import digest, serial
from .models import User

READ_PERMISSION = {'records':'records.read', 'participations':'records.read',
                   'qualifications':'qualification.read', 'teachers':'users.manage'}


def require_import_permission(actor, kind):
    actor.require('import')
    permission = READ_PERMISSION.get(kind)
    if permission is None:
        raise HTTPException(422, '导入类型无效')
    actor.require(permission)
    if kind == 'teachers':
        actor.require_admin()


def _principal(actor):
    # Deliberately exclude the inventory of all teachers: adding an unrelated
    # colleague must not invalidate a pending import. Referenced IDs are checked
    # separately, so moving a referenced person out of scope still denies access.
    return digest({'owner':actor.id, 'principal_revision':actor.user.auth_version,
        'role':actor.role.id, 'role_revision':actor.role.version,
        'administrator':actor.user.is_admin, 'org':actor.org.id,
        'orgs':sorted(actor.org_ids), 'permissions':sorted(actor.permissions)})


def make_import_proof(actor, kind, checked_rows):
    require_import_permission(actor, kind)
    people=set(); organizations=set()
    for row in checked_rows:
        value=row.get('normalized') or {}
        teacher=value.get('teacher_id')
        org=value.get('org_id')
        if teacher and teacher in actor.teacher_ids:
            people.add(teacher)
        if org and org in actor.org_ids:
            organizations.add(org)
    return {'schema_version':1, 'kind':kind, 'principal':_principal(actor),
            'teacher_ids':sorted(people), 'org_ids':sorted(organizations)}


def require_import_access(db, actor, job):
    if job.owner_id != actor.id:
        raise HTTPException(404, '导入任务不存在')
    require_import_permission(actor, job.kind)
    proof=(job.receipt or {}).get('access_proof')
    invalid='导入授权已变化或缺少原授权记录，请重新上传；原业务与审计记录保留'
    if (not isinstance(proof,dict) or type(proof.get('schema_version')) is not int
        or proof['schema_version'] != 1 or proof.get('kind') != job.kind
        or proof.get('principal') != _principal(actor)):
        raise HTTPException(409, invalid)
    for key in ('teacher_ids','org_ids'):
        values=proof.get(key)
        if (not isinstance(values,list) or any(not isinstance(v,str) or not v for v in values)
            or len(set(values)) != len(values)):
            raise HTTPException(409, invalid)
    if (not set(proof['teacher_ids']) <= set(actor.teacher_ids)
        or not set(proof['org_ids']) <= set(actor.org_ids)):
        raise HTTPException(403, '导入所涉人员或组织已不在当前授权范围')
    # Teacher-account import creates new people. Check receipt targets as well;
    # otherwise an account moved out of scope could remain visible via staging.
    if job.kind == 'teachers' and job.state == 'COMMITTED':
        ids=[row.get('object_id') for row in (job.receipt or {}).get('rows',[])]
        if ids:
            users=db.scalars(select(User).where(User.id.in_(ids))).all()
            if len(users)!=len(set(ids)) or any(u.org_id not in actor.org_ids for u in users):
                raise HTTPException(403, '导入生成账号已不在当前授权范围')


def public_import(job):
    data=serial(job)
    if job.state=='PREVIEW' and job.errors:data['state']='INVALID'
    data['receipt']=deepcopy(data.get('receipt') or {})
    data['receipt'].pop('access_proof', None)
    data['access_revoked']=False
    return data


def import_summary(db, actor, job):
    try:
        require_import_access(db, actor, job)
    except HTTPException as exc:
        if exc.status_code not in {403,409}:
            raise
        # Preserve a discoverable audit reference, but never return former rows,
        # generated object IDs, filenames or checksums as an authorization bypass.
        return {'id':job.id,'kind':job.kind,'state':'INVALID' if job.state=='PREVIEW' and job.errors else job.state,'version':job.version,
                'created_at':serial(job.created_at),'filename':'导入批次（访问已受限）',
                'total':None,'errors':None,'receipt':{},'access_revoked':True,
                'access_note':'授权已变化或旧批次缺少授权来源。请重新上传；历史审计保留。'}
    return public_import(job)
