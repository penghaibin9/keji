#!/usr/bin/env python3
"""Generate an auditable API endpoint catalog from the source security inventory."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from route_security_audit import audit


def render(root:Path):
    result=audit(root)
    lines=['# API 接口目录','',
      '> 由 `scripts/generate_api_catalog.py` 从当前源码自动生成。认证原语列只表示源码入口使用标准服务端认证/事务原语，不能替代运行时越权测试。','',
      f"当前 API 路由：**{result['route_count']}**；静态认证门：**{result['status']}**。",'',
      '| 方法 | 路径 | 模块文件 | 处理函数 | 认证/事务原语 | 公开 |','|---|---|---|---|---|---|']
    for r in sorted(result['routes'],key=lambda x:(x['path'],x['method'])):
        prim=', '.join(r['auth_primitives']) or '—'
        lines.append(f"| {r['method']} | `{r['path']}` | `{r['file']}` | `{r['function']}` | {prim} | {'是' if r['public'] else '否'} |")
    lines += ['', '## 使用边界','',
      '- `/api/auth/login` 是当前唯一公开业务 API；其他接口必须进入服务端认证/权限路径。',
      '- 路由目录不包含学校 SSO、数据中台和湘培的外部协议细节；外部协议以真实联调文档和责任方签认为准。',
      '- 生产 OpenAPI/Swagger 默认关闭；本文件用于交付、审计和版本比对。','']
    return '\n'.join(lines),result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));ap.add_argument('--output',default='docs/API_ENDPOINT_CATALOG.md');a=ap.parse_args()
    root=Path(a.root).resolve();text,result=render(root);out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text,encoding='utf-8')
    print(json.dumps({'status':result['status'],'route_count':result['route_count'],'output':str(out)},ensure_ascii=False))
