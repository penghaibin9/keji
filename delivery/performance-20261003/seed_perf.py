"""Seed a fresh, disposable SQLite DB with synthetic school-scale data for a local perf test.

Base structure via the project's own init tool (app.cli.init_empty); bulk synthetic
volume via the project's own ORM models. Writes credentials CSV to the lab dir only.
"""
from __future__ import annotations
import csv, json, os, random, secrets, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

PROJ = Path(sys.argv[1]).resolve(); LAB = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(PROJ / 'backend'))
LAB.mkdir(parents=True, exist_ok=True)
DB = LAB / 'perf.sqlite'
if DB.exists(): raise SystemExit('refuse: database already exists, use a new lab dir')
os.environ['ND_SCHOOL_NAME'] = '本机性能测试合成学校'
from sqlalchemy import insert, select, func, text
from sqlalchemy.orm import Session
from app.config import Settings
from app.main import create_app  # registers every table
from app.models import *
from app.org_assessment import OrganizationAssessment, OrganizationAssessmentRule
from app.reference_data import TrainingProjectMaster, TrainingCourseMaster, TrainingClassMaster
from app.passwords import HASHER
from app.core import serial, digest
from app import cli
from app.assessment_evidence import teacher_identity, organization_chain

random.seed(20261003)
t0 = time.time()
url = 'sqlite:///' + DB.as_posix()
cfg = Settings(env='test', database_url=url, secure_cookie=False, allowed_hosts='127.0.0.1,localhost',
               public_origin='http://127.0.0.1', storage_dir=LAB / 'files')
app = create_app(cfg); engine = app.state.engine
with engine.connect() as c:
    c.exec_driver_sql('PRAGMA journal_mode=WAL'); c.commit()
Base.metadata.create_all(engine)
pw = LAB / 'admin_pw.txt'; pw.write_text('Admin' + secrets.token_urlsafe(16) + '9', encoding='utf-8')
cli.init_empty(cfg, pw)
print('init_empty ok', round(time.time() - t0, 1), flush=True)

N_COLLEGE, N_DEPT_PER, N_TEACHER_PER_DEPT, N_SCHOOL_MGR = 20, 5, 32, 10
now = utcnow()
COLLEGE_NAMES = ['机电工程','信息工程','经济管理','建筑工程','汽车工程','医药卫生','艺术设计','外国语','财会金融','电子商务',
                 '物流管理','旅游酒店','智能制造','交通运输','食品工程','化工材料','环境工程','农林科技','体育健康','继续教育']
orgs, colleges, depts = [], [], []
for ci in range(N_COLLEGE):
    cid = str(uuid.uuid4()); colleges.append(cid)
    orgs.append(dict(id=cid, created_at=now, code=f'C{ci+1:02d}', name=COLLEGE_NAMES[ci] + '学院', kind='college', parent_id='school', active=True, version=1))
for ci, cid in enumerate(colleges):
    for di in range(N_DEPT_PER):
        did = str(uuid.uuid4()); depts.append((did, cid))
        orgs.append(dict(id=did, created_at=now, code=f'C{ci+1:02d}D{di+1}', name=f'{COLLEGE_NAMES[ci]}第{di+1}教研室', kind='dept', parent_id=cid, active=True, version=1))

SURN = '王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈'
GIVEN = '伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚桂英华建国志红文斌海燕晨宇欣怡子轩浩然雨涵思远'
def cname(): return random.choice(SURN) + ''.join(random.choice(GIVEN) for _ in range(random.choice((1, 2))))

users, creds = [], []  # creds: (username,password,role,user_id)
def mkuser(username, kind, org_id, staff_no=None):
    uid_ = str(uuid.uuid4()); pwd = 'Perf' + secrets.token_urlsafe(12) + '7'
    users.append(dict(id=uid_, created_at=now, username=username, name=cname(), staff_no=staff_no, title='讲师' if kind == 'teacher' else '负责人',
                      org_id=org_id, role_id='role-' + kind, password_hash=None, active=True, is_admin=False, must_change_password=False,
                      auth_version=1, version=1, failures=0, locked_until=None))
    creds.append((username, pwd, kind, uid_))
teachers = []
n = 0
for did, cid in depts:
    for _ in range(N_TEACHER_PER_DEPT):
        n += 1; mkuser(f't{n:05d}', 'teacher', did, f'JS{n:05d}'); teachers.append((users[-1]['id'], did))
for i, (did, cid) in enumerate(depts): mkuser(f'dept{i+1:03d}', 'dept', did)
for i, cid in enumerate(colleges): mkuser(f'college{i+1:02d}', 'college', cid)
for i in range(N_SCHOOL_MGR): mkuser(f'school{i+1:02d}', 'school', 'school')

def h(p): return HASHER.hash(p)
with ThreadPoolExecutor(max_workers=os.cpu_count()) as ex:
    hashes = list(ex.map(h, [c[1] for c in creds]))
for u, hh in zip(users, hashes): u['password_hash'] = hh
print('hashed', len(users), round(time.time() - t0, 1), flush=True)
with open(LAB / 'users.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['username', 'password', 'role', 'user_id'])
    for c in creds: w.writerow(c)

with Session(engine) as db:
    admin_id = db.scalar(select(User.id).where(User.username == 'admin'))
    db.execute(insert(Org), orgs); db.execute(insert(User), users); db.commit()
    p25 = Period(id=str(uuid.uuid4()), name='2025年度考核周期', start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), state='CLOSED')
    p26 = Period(id=str(uuid.uuid4()), name='2026年度考核周期', start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), state='OPEN')
    db.add_all([p25, p26]); db.flush()
    rules = {}
    for p in (p25, p26):
        cfgr = {'components': [{'key': 'hours', 'label': '授课学时', 'weight': '40'}, {'key': 'income', 'label': '培训收入', 'weight': '40'},
                               {'key': 'qualification', 'label': '资质', 'weight': '20'}]}
        r = Rule(kind='assessment', name=p.name + '教师考核规则', version_no=1, period_id=p.id, config=cfgr, fingerprint=digest(cfgr),
                 state='ACTIVE', created_by=admin_id, reason='合成性能测试规则'); db.add(r); rules[p.id] = r
        oc = {'components': [{'key': 'income', 'label': '培训收入', 'weight': '60', 'target': '1000000', 'source': '培训台账'},
                             {'key': 'teachers', 'label': '参与教师', 'weight': '40', 'target': '30', 'source': '培训台账'}]}
        for kind in ('college', 'dept'):
            db.add(OrganizationAssessmentRule(target_kind=kind, name=f'{p.name}{kind}组织考核', version_no=1, period_id=p.id, config=oc,
                   fingerprint=digest({'target_kind': kind, 'period_id': p.id, 'config': oc}), state='ACTIVE', created_by=admin_id, reason='合成'))
    db.commit()
    orules = {(r.target_kind, r.period_id): r for r in db.scalars(select(OrganizationAssessmentRule))}

    # Master data
    projects = [(f'P{i:04d}', f'{random.choice(COLLEGE_NAMES)}社会培训项目{i}') for i in range(1, 241)]
    courses = [(f'K{i:05d}', f'培训课程{i}', projects[i % len(projects)][0]) for i in range(1, 961)]
    classes = [(f'B{i:05d}', f'培训班{i}期', courses[i % len(courses)]) for i in range(1, 3601)]
    db.execute(insert(TrainingProjectMaster), [dict(id=str(uuid.uuid4()), created_at=now, code=c, name=nm, external_key=None, start_date=date(2025, 1, 1), end_date=date(2026, 12, 31), active=True, source='合成', version=1) for c, nm in projects])
    db.execute(insert(TrainingCourseMaster), [dict(id=str(uuid.uuid4()), created_at=now, code=c, name=nm, project_code=pc, external_key=None, active=True, source='合成', version=1) for c, nm, pc in courses])
    db.execute(insert(TrainingClassMaster), [dict(id=str(uuid.uuid4()), created_at=now, code=c, name=nm, project_code=co[2], course_code=co[0], start_date=None, end_date=None, active=True, source='合成', version=1) for c, nm, co in classes])
    db.commit()

    # Training records: ~20 per teacher, Jan 2025 .. Sep 2026
    recs = []; k = 0; start = date(2025, 1, 1); span = (date(2026, 9, 30) - start).days
    for tid, did in teachers:
        for _ in range(random.randint(12, 28)):
            k += 1; cl = random.choice(classes); co = cl[2]; pr = next(p for p in projects if p[0] == co[2]) if False else (co[2], '')
            recs.append(dict(id=str(uuid.uuid4()), created_at=now, external_key=f'REC-{k:07d}', teacher_id=tid,
                             event_date=start + timedelta(days=random.randint(0, span)), project_code=co[2], project=f'社会培训项目{co[2][1:]}',
                             course_code=co[0], course=co[1], class_code=cl[0], class_name=cl[1], hours=Decimal(random.randint(2, 40)),
                             participants=random.randint(10, 60), income=Decimal(random.randint(500, 20000)), source='合成性能测试', batch_id=None, state='VALID', version=1))
    for i in range(0, len(recs), 5000): db.execute(insert(TrainingRecord), recs[i:i + 5000])
    db.commit(); print('records', len(recs), round(time.time() - t0, 1), flush=True)

    # Qualifications: 2 per teacher
    today = date.today(); quals = []
    for tid, did in teachers:
        for j in range(2):
            r = random.random(); st = 'APPROVED' if r < .6 else 'SUBMITTED' if r < .8 else 'DRAFT' if r < .9 else 'RETURNED'
            exp = None
            if st == 'APPROVED':
                x = random.random(); exp = today + timedelta(days=random.randint(-90, -1) if x < .05 else random.randint(0, 30) if x < .13 else random.randint(31, 1500))
            quals.append(dict(id=str(uuid.uuid4()), created_at=now - timedelta(minutes=random.randint(0, 500000)), teacher_id=tid,
                              category=random.choice(['职业资格', '教学资质']), name=random.choice(['高级培训师', '职业技能等级证书', '双师型教师', '企业实践证明', '心理咨询师', '会计师']),
                              certificate_no=f'CERT-{tid[:8]}-{j}', issuer='合成发证机构', obtained=date(2020, 1, 1) + timedelta(days=random.randint(0, 2000)),
                              expires=exp, state=st, version=1, current_revision_id=None, attachment_ids=[]))
    db.execute(insert(Qualification), quals); db.commit(); print('qualifications', len(quals), flush=True)

    # Teacher assessments for both periods; 2025 archived with real verifiable archive payloads.
    archiver = SimpleNamespace(id=admin_id, name='学校系统管理员', org=SimpleNamespace(id='school'))
    st26 = ['TEACHER'] * 30 + ['DEPARTMENT'] * 25 + ['COLLEGE'] * 20 + ['SCHOOL'] * 15 + ['READY'] * 10
    objs = []
    for p in (p25, p26):
        for tid, did in teachers:
            sc = Decimal(random.randint(4500, 9990)) / 100
            detail = [{'key': 'hours', 'score': str((sc * Decimal('0.4')).quantize(Decimal('0.01')))}, {'key': 'income', 'score': str((sc * Decimal('0.4')).quantize(Decimal('0.01')))},
                      {'key': 'qualification', 'score': str(sc - 2 * (sc * Decimal('0.4')).quantize(Decimal('0.01')))}]
            o = Assessment(id=str(uuid.uuid4()), teacher_id=tid, period_id=p.id, rule_id=rules[p.id].id, score=sc, detail=detail,
                           source_snapshot={'records': random.randint(5, 30), 'synthetic': True}, state='READY' if p is p25 else random.choice(st26),
                           returned=random.random() < .04, version=3); objs.append(o)
    db.add_all(objs); db.flush()
    for o in objs:
        if o.period_id != p25.id: continue
        identity = teacher_identity(db, o.teacher_id)
        frozen = {k: v for k, v in serial(o).items() if k not in {'archive', 'archive_sha256'}}; frozen.update(state='ARCHIVED', version=o.version + 1)
        at = now.isoformat()
        payload = {'schema_version': 2, 'assessment': frozen, 'school_name': '本机性能测试合成学校', 'rule': serial(rules[o.period_id]), 'period': serial(p25),
                   'teacher': identity, 'organization_chain': organization_chain(db, identity['org_id']), 'source_snapshot': dict(o.source_snapshot),
                   'events': [{'actor_id': admin_id, 'actor_name': '学校系统管理员', 'org_id': 'school', 'action': '考核归档', 'created_at': at, 'reason': '合成归档', 'basis': ''}],
                   'archived_by': admin_id, 'archived_by_name': '学校系统管理员', 'archived_at': at, 'reason': '合成归档', 'basis': ''}
        o.archive = payload; o.archive_sha256 = digest(payload); o.state = 'ARCHIVED'; o.version += 1
    db.commit(); print('assessments', len(objs), round(time.time() - t0, 1), flush=True)

    # Organization assessments (not archived): colleges + depts for both periods
    oas = []
    for p in (p25, p26):
        for kind, ids in (('college', colleges), ('dept', [d for d, _ in depts])):
            r = orules[(kind, p.id)]
            for oid in ids:
                sc = Decimal(random.randint(5000, 9800)) / 100
                oas.append(dict(id=str(uuid.uuid4()), created_at=now, target_kind=kind, target_id=oid, period_id=p.id, rule_id=r.id, score=sc,
                                detail=[{'key': 'income', 'score': str(sc)}], source_snapshot={'target': {'id': oid, 'kind': kind}, 'period': {'id': p.id}},
                                state=('SCHOOL_APPROVED' if p is p25 else random.choice(['GENERATED', 'GENERATED', 'REVIEWED'])), version=1,
                                generated_by=admin_id, reviewed_by=None, school_audited_by=None, archive=None, archive_sha256=None))
    db.execute(insert(OrganizationAssessment), oas)
    # Disputes and notices
    dps = [dict(id=str(uuid.uuid4()), created_at=now, teacher_id=random.choice(teachers)[0], object_type='record', object_id=str(uuid.uuid4()), period_id=p26.id,
                reason='合成：课时数与教务记录不一致，请核对', state='OPEN', resolution='', resolved_by=None, version=1) for _ in range(400)]
    db.execute(insert(Dispute), dps)
    db.execute(insert(Notice), [dict(id=str(uuid.uuid4()), created_at=now, title=f'合成通知{i}', body='合成性能测试通知正文' * 20, category='业务通知', org_id='school', author_id=admin_id, published=True, version=1) for i in range(60)])
    db.commit()
    counts = {t: db.scalar(text(f'select count(*) from {t}')) for t in ('organizations', 'users', 'training_records', 'qualifications', 'assessments', 'organization_assessments', 'disputes', 'notices', 'training_projects', 'training_courses', 'training_classes', 'audit_events')}
cli.check(cfg)
counts['journal_mode'] = 'wal'; counts['seed_seconds'] = round(time.time() - t0, 1)
(LAB / 'seed_counts.json').write_text(json.dumps(counts, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps(counts, ensure_ascii=False))
