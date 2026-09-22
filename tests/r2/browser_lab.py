"""Creates ONE disposable synthetic database then runs the real app on loopback.

Refuses non-test directories/nonempty databases. Not a production install tool.
The DB has no fabricated Alembic head: /api/health should remain not_ready.
"""
from pathlib import Path
import sys,os
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(Path(__file__).parent)]
from app.config import Settings
from app.main import create_app
from support import populate
import uvicorn

def make_lab(root):
    root=Path(root).resolve()
    if not root.name.startswith('nd-r2-test-'):raise RuntimeError('Lab must use a dedicated nd-r2-test- directory')
    root.mkdir(parents=True,exist_ok=True)
    if (root/'browser.sqlite').exists():raise RuntimeError('Refusing to overwrite an existing lab database')
    cfg=Settings(env='test',database_url='sqlite:///'+str(root/'browser.sqlite'),secure_cookie=False,
        allowed_hosts='127.0.0.1,localhost',public_origin='http://127.0.0.1:8768',storage_dir=root/'files')
    app=create_app(cfg);populate(app.state.engine,first_login=True)
    return app
if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Supply a new /tmp/nd-r2-test-* directory')
    uvicorn.run(make_lab(sys.argv[1]),host='127.0.0.1',port=8768,access_log=False)
