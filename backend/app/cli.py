"""Explicit empty-school initialization and consistency checks."""
from __future__ import annotations
import argparse,os
from pathlib import Path
from sqlalchemy import select,func
from sqlalchemy.orm import sessionmaker
from . import installation  # register immutable installation provenance
from .config import Settings
from .core import make_engine
from .models import Base,Org,Role,User,Guard,Setting,Connection
from .permissions import ALLOWED
from .passwords import hash_password
from .readiness import _setting_ok
from .settings_catalog import DEFAULT_BUSINESS_DICTIONARY,DEFAULT_IMPORT_POLICY
# Register extension tables; never create them here.
from . import org_assessment,integrations  # noqa:F401


def _sessions(cfg):return make_engine(cfg.database_url)

def init_empty(cfg,password_file):
    school_name=os.environ.get('ND_SCHOOL_NAME','').strip()
    if not school_name or len(school_name)>120:raise RuntimeError('ND_SCHOOL_NAME must be explicitly configured')
    p=Path(password_file)
    if p.is_symlink() or not p.is_file():raise RuntimeError('administrator password secret missing')
    password=p.read_text().rstrip('\r\n')
    if len(password)<12:raise RuntimeError('administrator password secret too short')
    engine=_sessions(cfg)
    try:
        if cfg.env == "production":
            with engine.connect() as connection: installation.require_canonical(connection, require_mysql=True)
        with sessionmaker(bind=engine,expire_on_commit=False).begin() as db:
            if db.scalar(select(func.count()).select_from(User)) or db.scalar(select(func.count()).select_from(Org)):
                raise RuntimeError('initialization refuses a non-empty business database')
            root=Org(id='school',code='school',name=school_name,kind='school',parent_id=None,active=True);db.add(root)
            for kind in ('teacher','dept','college','school'):
                db.add(Role(id='role-'+kind,code=kind,name={'teacher':'普通教师','dept':'教研室负责人','college':'学院负责人','school':'学校管理员'}[kind],kind=kind,permissions=sorted(ALLOWED[kind]),active=True))
            db.flush()
            db.add(User(username='admin',name='学校系统管理员',staff_no=None,title='系统管理员',org_id='school',role_id='role-school',password_hash=hash_password(password),active=True,is_admin=True,must_change_password=True))
            db.add(Guard(key='calculations',version=1))
            db.add_all([
              Connection(code='sso',name='学校统一认证',state='NOT_CONNECTED',mappings=[],config={'endpoint':'','owner':'','retry_count':3,'secret_env':'','frequency_minutes':30,'auth_mode':'school_sso'}),
              Connection(code='middle',name='学校数据中台',state='NOT_CONNECTED',mappings=[],config={'endpoint':'','owner':'','retry_count':3,'secret_env':'','frequency_minutes':30,'auth_mode':'token'}),
              Connection(code='province',name='湘培直通车',state='NOT_CONNECTED',mappings=[],config={'endpoint':'','owner':'','retry_count':3,'secret_env':'','frequency_minutes':30,'auth_mode':'custom'}),
              Setting(key='branding',value={'school_name':school_name},version=1),
              Setting(key='metrics',value={'income_note':'培训收入统计口径待学校确认','participants_note':'课程人次统计口径待学校确认'},version=1),
              Setting(key='qualification',value={'expiry_days':30,'categories':['职业资格','教学资质','双师型教师（初级）','双师型教师（中级）','双师型教师（高级）','职业技能等级证书','培训师资格']},version=1),
              Setting(key='business_dictionary',value=DEFAULT_BUSINESS_DICTIONARY,version=1),
              Setting(key='import_policy',value=DEFAULT_IMPORT_POLICY,version=1),
            ])
    finally:engine.dispose()


def check(cfg):
    engine=_sessions(cfg)
    try:
        if cfg.env == "production":
            with engine.connect() as connection: installation.require_canonical(connection, require_mysql=True)
        with sessionmaker(bind=engine)() as db:
            roots=db.scalars(select(Org).where(Org.kind=='school',Org.parent_id.is_(None),Org.active.is_(True))).all()
            if len(roots)!=1:raise RuntimeError('school root invalid')
            roles={r.kind for r in db.scalars(select(Role).where(Role.active.is_(True)))}
            if not {'teacher','dept','college','school'}<=roles:raise RuntimeError('core roles incomplete')
            guard=db.get(Guard,'calculations')
            if not guard:raise RuntimeError('mutation guard missing')
            for key in ('branding','metrics','qualification','business_dictionary','import_policy'):
                obj=db.get(Setting,key)
                if not obj or not _setting_ok(key,obj.value):raise RuntimeError('required setting invalid')
            admins=db.scalar(select(func.count()).select_from(User).where(User.active.is_(True),User.is_admin.is_(True))) or 0
            if admins<1:raise RuntimeError('active administrator missing')
            connections={x.code:x for x in db.scalars(select(Connection)).all()}
            if set(connections)!={'sso','middle','province'}:raise RuntimeError('required procurement interface registrations incomplete')
            if any(x.state not in {'NOT_CONNECTED','CONNECTED'} for x in connections.values()):raise RuntimeError('interface connection state invalid')
    finally:engine.dispose()


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    i=sub.add_parser('init');i.add_argument('--password-file',required=True)
    sub.add_parser('check')
    a=p.parse_args();cfg=Settings()
    try:
        if a.cmd=='init':init_empty(cfg,a.password_file)
        else:check(cfg)
    except RuntimeError as exc:
        print('BLOCK:',str(exc));raise SystemExit(2)
    print('OK:',a.cmd)

if __name__=='__main__':main()
