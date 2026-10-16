"""本机演示：用合成测试数据临时启动系统，看新增页面效果。不连正式数据库，关掉即清空。

用法（仓库根目录）：
    pip install -r backend/requirements.txt pytest
    python scripts/local_demo.py            # 然后浏览器打开 http://127.0.0.1:8765
账号口令见启动后的提示。数据存在系统临时目录，Ctrl+C 退出后可删除。
"""
import pathlib, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests' / 'r2'), str(ROOT / 'tests')]
import uvicorn
from app.config import Settings
from app.main import create_app
from app.models import Setting, User
from app.reference_data import TeacherCourseTerm, TrainingCourseMaster
from support import populate, HASH, FIXTURE_PASSWORD

PORT = 8765
ORIGIN = f'http://127.0.0.1:{PORT}'
tmp = pathlib.Path(tempfile.mkdtemp(prefix='yueke_demo_'))
app = create_app(Settings(env='test', database_url='sqlite:///' + str(tmp / 'demo.sqlite'), secure_cookie=False, public_origin=ORIGIN,
                          allowed_hosts='127.0.0.1,localhost', storage_dir=tmp / 'files'))
populate(app.state.engine)
EXTRA = (('reviewer', '继续教育学院审核人'), ('hruser', '组织人事部办理人'), ('jwcuser', '教务处办理人'))
with app.state.sessions.begin() as db:
    for ident, name in EXTRA:
        db.add(User(id=ident, username=ident, name=name, org_id='school', role_id='role-school', password_hash=HASH, must_change_password=False, active=True))
    db.add(Setting(key='social_training_duties', value={'coordinator': ['reviewer'], 'trainer_hr': ['hruser'], 'trainer_filing': ['jwcuser']}))
    db.add(TrainingCourseMaster(code='OLD-1', name='早先登记的课', project_code=None, source='学校人工登记'))
    db.add(TeacherCourseTerm(external_key='JW|J001|K9|2026-2027-1', origin='JW', staff_no='J001', teacher_name='测试教师一', course_code='K9',
                             course_name='茶艺与健康', term_name='2026-2027-1', credit=2, hours=32, source='演示', extra={}))
print('\n演示系统已启动：', ORIGIN)
print('统一口令：', FIXTURE_PASSWORD)
print('账号：teacher(老师) depthead(教研室) collegehead(学院) schooladmin(学校管理员) reviewer(继续教育学院) hruser(组织人事部) jwcuser(教务处)')
print('建议看：老师首页“业务办理”四个入口；学院“培训项目”里申报并选校外；学校“培训师资库”。Ctrl+C 退出。\n')
uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')
