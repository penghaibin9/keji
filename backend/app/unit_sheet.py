"""2026-11-09 老师上传一张参训明细表（Excel）导入本项目参训明细。

表只有五列：培训日期、课程、学员、是否完成、授课教师工号。只有“培训日期”“学员”必填；
课程只有一门时可不填；是否完成不填按“是”；授课教师工号不填按项目负责人。
再次上传会替换之前上传的明细。
"""
import re
import zipfile
from datetime import date, datetime
from io import BytesIO
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import select
from .models import User
from .reference_data import TrainingCourseMaster

HEADERS = ['培训日期', '课程', '学员', '是否完成', '授课教师工号']
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
KEY_PREFIX = 'xls:'


def template_bytes():
    wb = Workbook(); ws = wb.active; ws.title = '参训明细'; ws.append(HEADERS); ws.freeze_panes = 'A2'
    fill = PatternFill('solid', fgColor='D9EAF7')
    for cell, width in zip(ws[1], (14, 22, 18, 10, 20)):
        cell.font = Font(bold=True); cell.fill = fill
        ws.column_dimensions[cell.column_letter].width = width
    wb.properties.title = '参训明细表'
    out = BytesIO(); wb.save(out); wb.close(); return out.getvalue()


def _date(v):
    if isinstance(v, datetime): return v.date()
    if isinstance(v, date): return v
    m = re.fullmatch(r'\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*', str(v or ''))
    if not m: return None
    try: return date(*map(int, m.groups()))
    except ValueError: return None


def _text(v):
    if v is None: return ''
    if isinstance(v, float) and v.is_integer(): v = int(v)
    return str(v).strip()


def read_rows(data, filename):
    if not filename or not filename.lower().endswith('.xlsx'): raise HTTPException(422, '请上传 .xlsx 格式的参训明细表')
    if not data or len(data) > MAX_BYTES: raise HTTPException(413, '表格不能超过 5 MB')
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > 500 or sum(x.file_size for x in infos) > 100 * 1024 * 1024 or any('vbaproject' in x.filename.lower() for x in infos): raise ValueError
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True, keep_links=False)
    except Exception: raise HTTPException(422, '表格打不开，请用下载的模板重新填写') from None
    try:
        rows = wb.worksheets[0].iter_rows(values_only=True)
        head = [_text(x) for x in (next(rows, None) or [])]
        if not {'培训日期', '学员'} <= set(head): raise HTTPException(422, '表头不对，请用下载的模板填写（至少要有“培训日期”“学员”两列）')
        idx = {h: head.index(h) for h in HEADERS if h in head}
        out = []
        for n, row in enumerate(rows, start=2):
            vals = {h: (row[i] if i < len(row) else None) for h, i in idx.items()}
            if all(_text(v) == '' for v in vals.values()): continue
            out.append((n, vals))
            if len(out) > MAX_ROWS: raise HTTPException(413, f'一次最多 {MAX_ROWS} 行')
        return out
    finally: wb.close()


def build_units(db, project, rows, filename, actor=None):
    """返回 (UnitData 字典列表, 错误列表, 有效行数)。错误行跳过，其余照常导入。"""
    code = project.data['code']; mode = project.data['mode']
    courses = list(db.scalars(select(TrainingCourseMaster).where(TrainingCourseMaster.project_code == code, TrainingCourseMaster.active == True)))
    if not courses: raise HTTPException(409, '项目还没有登记课程，请先在项目里添加课程')
    by_key = {}
    for c in courses: by_key[c.code] = c; by_key.setdefault(c.name, c)
    owner = db.get(User, project.owner_id)
    staff_cache = {}
    allowed = set()
    errors, groups, ok = [], {}, 0
    start, end = project.data['start_date'], project.data['end_date']
    for n, v in rows:
        d = _date(v.get('培训日期')); learner = _text(v.get('学员'))[:200]
        course_text = _text(v.get('课程')); done_text = _text(v.get('是否完成')); staff_text = _text(v.get('授课教师工号'))
        if not d: errors.append({'row': n, 'reason': '培训日期没填或格式不对'}); continue
        if not start <= d.isoformat() <= end: errors.append({'row': n, 'reason': f'培训日期不在项目期间（{start} 至 {end}）'}); continue
        if not learner: errors.append({'row': n, 'reason': '学员没填'}); continue
        if course_text: course = by_key.get(course_text)
        else: course = courses[0] if len(courses) == 1 else None
        if not course: errors.append({'row': n, 'reason': ('课程“' + course_text + '”不是本项目的课程') if course_text else '本项目有多门课程，请填写课程'}); continue
        if done_text and done_text not in {'是', '否', '完成', '未完成', 'Y', 'N', 'y', 'n'}: errors.append({'row': n, 'reason': '是否完成只能填“是”或“否”'}); continue
        done = done_text in {'', '是', '完成', 'Y', 'y'}
        teachers, bad = [], ''
        for s in [x for x in re.split(r'[、,，;；\s]+', staff_text) if x] or [None]:
            if s is None: user = owner
            else:
                if s not in staff_cache: staff_cache[s] = db.scalar(select(User).where(User.staff_no == s, User.active == True))
                user = staff_cache[s]
            if not user: bad = '找不到工号 ' + s + ' 的老师'; break
            if user.id not in allowed:
                if not _may_name(db, actor, project, owner, user): bad = '工号 ' + (s or '') + ' 的老师不在本院，不能填'; break
                allowed.add(user.id)
            teachers.append(user.id)
        if bad: errors.append({'row': n, 'reason': bad}); continue
        key = (d.isoformat(),) if mode == 'person_day' else (course.code, d.isoformat())
        g = groups.setdefault(key, {'course': course, 'date': d, 'learners': {}, 'teachers': []})
        if learner in g['learners']: errors.append({'row': n, 'reason': '学员“' + learner + '”同一天重复'}); continue
        g['learners'][learner] = done
        for t in teachers:
            if t not in g['teachers']: g['teachers'].append(t)
        ok += 1
    units = []
    for key, g in sorted(groups.items()):
        c, d = g['course'], g['date']
        units.append({'external_key': (KEY_PREFIX + project.id + ':' + ':'.join(key))[:128], 'course_code': c.code, 'class_code': code[:64],
                      'module': (c.name + ' ' + d.isoformat())[:200], 'event_date': d, 'mode': mode,
                      'learners': [{'reference': r, 'signed': x, 'hours_met': x, 'full_attendance': x, 'passed': x} for r, x in g['learners'].items()],
                      'teachers': [{'teacher_id': t, 'staff_type': 'internal', 'role': 'lecturer'} for t in g['teachers']],
                      'evidence_note': ('参训明细表 ' + filename)[:200]})
    return units, errors, ok, allowed


def _may_name(db, actor, project, owner, user):
    """授课教师：上传人授权范围内的老师；项目负责人上传时也可填本院（项目所属学院）在岗老师。"""
    if not user.staff_no or not user.active or user.authorization_pending: return False
    if actor is not None:
        try: actor.check_teacher(db, user.id, active=True); return True
        except HTTPException: pass
    if actor is None or actor.id != project.owner_id: return False
    from .approvals import college_of
    college = college_of(db, user)
    owner_college = college_of(db, owner)
    return college is not None and college.id in {project.org_id, owner_college.id if owner_college else None}
