"""运行过程接口（2026-11-07）：档案视图、运行记录、申请变更、年度确认、停用与恢复。规则见 app/lifecycle.py。"""
from fastapi import APIRouter, Request, HTTPException
from ..core import command, read_operation, check_version
from ..social_models import SocialResource
from ..social_schemas import RunNoteIn, ChangeIn, ChangeAction, AnnualConfirmIn, LifeReason
from .. import lifecycle as lc

router = APIRouter(prefix='/api/social/lifecycle', tags=['培训运行过程'])



def _change(db, ident):
    obj = db.get(SocialResource, ident)
    if obj is None or obj.kind != 'change':
        raise HTTPException(404, '变更申请不存在')
    return obj


@router.get('/changes/{ident}')
def change_detail(ident: str, request: Request):
    return read_operation(request, 'portal.read', lambda db, a, s: lc.change_read(db, a, _change(db, ident)))


@router.post('/changes/{ident}/actions')
def change_act(ident: str, data: ChangeAction, request: Request):
    def apply(db, a, s):
        change = _change(db, ident)
        check_version(change, data.expected_version)
        lc.change_action(db, a, change, data.action, data.reason, data.basis)
        return lc.change_read(db, a, change)
    return command(request, data.model_dump(), 'portal.read', apply)


@router.get('/board/{kind}')
def running_board(kind: str, request: Request):
    return read_operation(request, 'portal.read', lambda db, a, s: lc.board(db, a, kind))


@router.get('/mine/{kind}')
def my_items(kind: str, request: Request):
    return read_operation(request, 'portal.read', lambda db, a, s: lc.my_items(db, a, kind))


@router.get('/queue/{kind}')
def approval_queue(kind: str, request: Request):
    return read_operation(request, 'portal.read', lambda db, a, s: lc.approval_queue(db, a, kind))


@router.get('/close-review/{ident}')
def close_review(ident: str, request: Request):
    return read_operation(request, 'portal.read', lambda db, a, s: lc.close_review(db, a, lc.load(db, a, 'project', ident)))


@router.get('/close-check/{ident}')
def close_check(ident: str, request: Request):
    def read(db, a, s):
        obj = lc.load(db, a, 'project', ident)
        return {'gaps': lc.close_gaps(db, obj), 'notes': lc.close_notes(db, obj), 'points': lc.points_line(db, obj)}
    return read_operation(request, 'portal.read', read)


@router.get('/{kind}/{ident}')
def archive(kind: str, ident: str, request: Request):
    return read_operation(request, 'portal.read', lambda db, a, s: lc.view(db, a, kind, lc.load(db, a, kind, ident)))


@router.post('/{kind}/{ident}/notes')
def note(kind: str, ident: str, data: RunNoteIn, request: Request):
    def apply(db, a, s):
        obj = lc.load(db, a, kind, ident, write=True)
        lc.add_note(db, a, kind, obj, data.tag, data.text, data.happened_on, data.reason)
        return lc.view(db, a, kind, obj)
    return command(request, data.model_dump(mode='json'), 'portal.read', apply)


@router.post('/{kind}/{ident}/changes')
def change_submit(kind: str, ident: str, data: ChangeIn, request: Request):
    def apply(db, a, s):
        obj = lc.load(db, a, kind, ident, write=True)
        result = lc.submit_change(db, a, kind, obj, data.values, data.reason, data.basis)
        return {**result, 'archive': lc.view(db, a, kind, obj)}
    return command(request, data.model_dump(mode='json'), 'portal.read', apply)


@router.post('/{kind}/{ident}/annual')
def annual(kind: str, ident: str, data: AnnualConfirmIn, request: Request):
    def apply(db, a, s):
        obj = lc.load(db, a, kind, ident, write=True)
        lc.annual_confirm(db, a, kind, obj, data.year, data.running, data.text, data.reason)
        return lc.view(db, a, kind, obj)
    return command(request, data.model_dump(mode='json'), 'portal.read', apply)


@router.post('/{kind}/{ident}/{operation}')
def stop_or_resume(kind: str, ident: str, operation: str, data: LifeReason, request: Request):
    def apply(db, a, s):
        if operation not in ('stop', 'resume'):
            raise HTTPException(404, '操作不存在')
        obj = lc.load(db, a, kind, ident, write=True)
        check_version(obj, data.expected_version)
        (lc.stop if operation == 'stop' else lc.resume)(db, a, kind, obj, data.reason)
        return lc.view(db, a, kind, obj)
    return command(request, data.model_dump(), 'portal.read', apply)
