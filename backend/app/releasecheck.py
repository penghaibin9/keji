"""Production start guard. Only the hashed fresh canonical graph can start; legacy remains unverified."""
from pathlib import Path
import importlib.util,json

def check_source_release():
    root=Path(__file__).resolve().parents[2]
    if root.name=='backend':root=root.parent
    path=root/'scripts/check_assembly.py'
    if not path.is_file():raise RuntimeError('发布核验工具缺失，禁止生产启动')
    spec=importlib.util.spec_from_file_location('nd_assembly',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    result=mod.inspect_assembly(root)
    if result['status']!='PASS':raise RuntimeError('当前源码或空库基线校验未通过，禁止生产启动')
    return result

if __name__=='__main__':
    try:print(json.dumps(check_source_release(),ensure_ascii=False))
    except RuntimeError as ex:print(str(ex));raise SystemExit(2)
