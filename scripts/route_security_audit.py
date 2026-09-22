#!/usr/bin/env python3
"""Static API security contract inventory.

Every API route except the explicitly allow-listed authentication bootstrap routes
must visibly invoke one of the canonical server-side authorization/transaction primitives. This is a source gate only;
runtime role/object tests remain authoritative for actual data scope.
"""
from __future__ import annotations
import ast, json, sys
from pathlib import Path

AUTH_PRIMITIVES={'read_operation','command','current_actor'}
PUBLIC={
    ('POST','/api/auth/login'),
    ('GET','/api/auth/sso/status'),
    ('GET','/api/auth/sso/start'),
    ('GET','/api/auth/sso/callback'),
}


def route_decorator(node):
    for d in node.decorator_list:
        call=d if isinstance(d,ast.Call) else None
        if not call or not isinstance(call.func,ast.Attribute):continue
        method=call.func.attr.upper()
        if method not in {'GET','POST','PUT','PATCH','DELETE'}:continue
        if not call.args or not isinstance(call.args[0],ast.Constant):continue
        return method,str(call.args[0].value)
    return None


def calls(node):
    return {n.func.id for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}


def prefix(tree):
    for n in tree.body:
        if isinstance(n,ast.Assign):
            for t in n.targets:
                if isinstance(t,ast.Name) and t.id=='router' and isinstance(n.value,ast.Call):
                    for kw in n.value.keywords:
                        if kw.arg=='prefix' and isinstance(kw.value,ast.Constant):return str(kw.value.value)
    return ''


def audit(root):
    root=Path(root);rows=[];violations=[]
    for p in sorted((root/'backend/app/routes').glob('*.py')):
        tree=ast.parse(p.read_text(encoding='utf-8'));pre=prefix(tree)
        for n in tree.body:
            if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            rd=route_decorator(n)
            if not rd:continue
            method,path=rd;full=pre+path
            cs=calls(n);public=(method,full) in PUBLIC
            protected=bool(cs&AUTH_PRIMITIVES)
            row={'file':str(p.relative_to(root)),'function':n.name,'method':method,'path':full,
                 'public':public,'auth_primitives':sorted(cs&AUTH_PRIMITIVES),'protected':protected}
            rows.append(row)
            if not public and not protected:violations.append(row)
    return {'status':'PASS' if not violations else 'FAIL','route_count':len(rows),'public_routes':sorted([f"{r['method']} {r['path']}" for r in rows if r['public']]),
            'violations':violations,'routes':rows,'note':'Static gate only; object/data-scope authorization still requires runtime negative tests.'}

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];result=audit(root)
    out=Path(sys.argv[1]) if len(sys.argv)>1 else None
    payload=json.dumps(result,ensure_ascii=False,indent=2)
    if out:out.parent.mkdir(parents=True,exist_ok=True);out.write_text(payload+'\n',encoding='utf-8')
    print(payload);raise SystemExit(0 if result['status']=='PASS' else 2)
