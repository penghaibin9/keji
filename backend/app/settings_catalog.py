"""Validated school-configurable dictionaries and safe runtime parameters.

Workflow state *codes* and legal transitions remain owned by server code. Schools may
change display labels for known codes, but cannot invent states or transitions here.
"""
from __future__ import annotations
from collections.abc import Mapping
from fastapi import HTTPException
from .models import Setting

STATUS_LABEL_DEFAULTS = {
    'DRAFT':'草稿','SUBMITTED':'待资质审核','APPROVED':'审核通过','RETURNED':'退回补充',
    'TEACHER':'教师确认','DEPARTMENT':'教研室确认','COLLEGE':'学院确认','SCHOOL':'学校审核',
    'READY':'待归档','ARCHIVED':'已归档','GENERATED':'待组织复核','REVIEWED':'待学校审核',
    'SCHOOL_APPROVED':'待归档','OPEN':'进行中','CLOSED':'已关闭','RESOLVED':'已解决',
    'ACTIVE':'已启用','INACTIVE':'已停用','VALID':'有效记录','PENDING':'排队中','RUNNING':'处理中',
    'RETRY':'等待重试','FAILED':'处理失败','BLOCKED':'未接通 / 已阻断','DONE':'已完成',
    'PREVIEW':'待确认导入','COMMITTED':'已入库','NOT_CONNECTED':'未对接','VALIDATED':'仅本地校验',
    'EXPIRING':'有效期核对','BASE':'初始积分','RECALC':'重算差额','MANUAL':'人工调整',
    'SUCCESS':'成功','DENIED':'已拦截','ERROR':'异常','VOID':'已作废',
}

DEFAULT_BUSINESS_DICTIONARY = {
    'notice_categories':['业务通知','政策通知','操作通知'],
    'record_sources':['经核对人工录入','Excel导入','学校数据中台'],
    'status_labels':dict(STATUS_LABEL_DEFAULTS),
}
DEFAULT_IMPORT_POLICY = {'max_rows':5000}


def _nonblank(value, max_len=160):
    return isinstance(value,str) and bool(value.strip()) and len(value.strip()) <= max_len


def _unique_text_list(value, *, max_items=100, max_len=80):
    return (isinstance(value,list) and 1 <= len(value) <= max_items
            and all(_nonblank(x,max_len) for x in value)
            and len({x.strip() for x in value}) == len(value))


def setting_ok(key, value):
    if not isinstance(value,Mapping):return False
    if key=='branding':return _nonblank(value.get('school_name'),120) and set(value)=={'school_name'}
    if key=='metrics':return set(value)=={'income_note','participants_note'} and all(_nonblank(value.get(k),2000) for k in ('income_note','participants_note'))
    if key=='qualification':
        days,categories=value.get('expiry_days'),value.get('categories')
        return (set(value)=={'expiry_days','categories'} and type(days) is int and 1<=days<=365
                and _unique_text_list(categories,max_items=100,max_len=80))
    if key=='business_dictionary':
        if set(value)!={'notice_categories','record_sources','status_labels'}:return False
        labels=value.get('status_labels')
        return (_unique_text_list(value.get('notice_categories'),max_items=50,max_len=40)
                and _unique_text_list(value.get('record_sources'),max_items=50,max_len=100)
                and isinstance(labels,Mapping) and set(labels)==set(STATUS_LABEL_DEFAULTS)
                and all(_nonblank(v,40) for v in labels.values()))
    if key=='import_policy':
        rows=value.get('max_rows')
        return set(value)=={'max_rows'} and type(rows) is int and 100<=rows<=10000
    return False


def require_setting(db,key):
    obj=db.get(Setting,key)
    if not obj or not setting_ok(key,obj.value):raise HTTPException(503,f'{key} 配置未初始化')
    return obj


def business_dictionary(db):
    return require_setting(db,'business_dictionary').value


def import_policy(db):
    return require_setting(db,'import_policy').value


def import_row_limit(db):
    return int(import_policy(db)['max_rows'])
