#!/usr/bin/env python3
"""Generate an auditable API endpoint catalog from the source security inventory."""
from __future__ import annotations
import argparse,ast,json
from pathlib import Path
from route_security_audit import audit,route_decorator


def render(root:Path):
    result=audit(root)
    result['business_route_count']=result['route_count']
    health=[node for node in ast.walk(ast.parse((root/'backend/app/main.py').read_text(encoding='utf-8')))
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and route_decorator(node)==('GET','/api/health')]
    assert len(health)==1,'健康接口声明缺失或重复'
    result['routes'].append({'method':'GET','path':'/api/health','file':'backend/app/main.py',
                            'function':health[0].name,'auth_primitives':[],'public':True,'protected':False})
    result['health_route_count']=len(health)
    result['route_count']=len(result['routes'])
    lines=['# 接口目录（交付候选）','',
      '> 由 `scripts/generate_api_catalog.py` 从当前源码自动生成。认证原语列只表示源码入口使用标准服务端认证/事务原语，不能替代运行时越权测试。','',
      f"当前接口共 **{result['route_count']}** 项：业务路由 **{result['business_route_count']}** 项、健康检查 **{result['health_route_count']}** 项；业务静态认证门：**{result['status']}**。",'',
      '| 方法 | 路径 | 模块文件 | 处理函数 | 认证/事务原语 | 公开 |','|---|---|---|---|---|---|']
    for r in sorted(result['routes'],key=lambda x:(x['path'],x['method'])):
        prim=', '.join(r['auth_primitives']) or '—'
        lines.append(f"| {r['method']} | `{r['path']}` | `{r['file']}` | `{r['function']}` | {prim} | {'是' if r['public'] else '否'} |")
    lines += ['', '## 使用边界','',
      '- 公开列按当前路由审计清单生成；登录、统一认证回调等公开入口仍需各自的票据、状态与防伪校验。',
      '- 健康检查是主程序的公开只读入口，另计1项；静态业务认证门仍核对业务路由目录，不将健康接口视为受业务角色授权的操作。',
      '- `GET /api/todos?stage=archive`：待归档清单；只接受 `archive` 这一筛选值，仍按当前角色权限、本人回避和组织范围筛选。实现见 `backend/app/routes/business.py`。',
      '- 路由目录不包含学校 SSO、数据中台和湘培的外部协议细节；外部协议以真实联调文档和责任方签认为准。',
      '- 生产 OpenAPI/Swagger 默认关闭；本文件用于交付、审计和版本比对。','']
    return '\n'.join(lines),result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));ap.add_argument('--output',default='docs/API_ENDPOINT_CATALOG.md');a=ap.parse_args()
    root=Path(a.root).resolve();text,result=render(root);out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text,encoding='utf-8', newline='\n')
    print(json.dumps({'status':result['status'],'route_count':result['route_count'],'output':str(out)},ensure_ascii=False))
