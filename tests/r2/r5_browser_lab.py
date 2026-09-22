"""Disposable synthetic browser lab. NOT production/MySQL/HTTPS acceptance."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(Path(__file__).parent)]
from app.main import create_app
from app.config import Settings
from app.models import Rule,Assessment
from support import populate
from sqlalchemy.orm import Session
import uvicorn

def build(root):
    root=Path(root).resolve()
    if not str(root).startswith('/tmp/nd-r5-test-'):raise RuntimeError('Use a new isolated /tmp/nd-r5-test-* directory')
    root.mkdir(parents=True,exist_ok=True)
    if (root/'browser.sqlite').exists():raise RuntimeError('Refusing existing database')
    cfg=Settings(env='test',database_url='sqlite:///'+str(root/'browser.sqlite'),secure_cookie=False,
       allowed_hosts='127.0.0.1,localhost',public_origin='http://127.0.0.1:8769',storage_dir=root/'files')
    app=create_app(cfg);populate(app.state.engine)
    with Session(app.state.engine) as db:
        rule=Rule(kind='assessment',name='浏览器合成考核规则',period_id='period2026',version_no=1,config={'components':[]},fingerprint='1'*64,created_by='schooladmin',reason='浏览器合成测试')
        db.add(rule);db.flush()
        for teacher,state,score in [('teacher','SCHOOL',85),('otherteacher','TEACHER',75)]:
            db.add(Assessment(teacher_id=teacher,period_id='period2026',rule_id=rule.id,score=score,state=state,detail=[],source_snapshot={}))
        db.commit()
    return app
if __name__=='__main__':uvicorn.run(build(sys.argv[1]),host='127.0.0.1',port=8769,access_log=False)
