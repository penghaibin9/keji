#!/usr/bin/env python3
"""Select school delivery files and block private state or internal documents."""
from __future__ import annotations
import argparse, ipaddress, json, os, re, zipfile
from pathlib import Path, PurePosixPath
from refresh_launcher_manifest import PRIVATE_DIRS, PRIVATE_SUFFIXES, ROOT_FILES, DEMO_ROOT_FILES

FOLDERS=('backend','frontend','deploy','scripts','tests','delivery','docs','acceptance')
EXCLUDED_FILES={
 'docs/20261011_Codex部署隐患排查.md', 'docs/20261011_Codex修改记录_Claude复审.md',
 'docs/20261011_交接_未完成事项.md', 'docs/20261012_复审与打包接收.md',
 'docs/20261011_Codex复审文件指纹.json',
 'docs/四角色核心业务流程走查修复方案_20261012.md',
 'delivery/Windows_受限访问.ps1', 'delivery/交付验证报告.json',
}
EXCLUDED_PREFIXES=('docs/历史版本/','docs/10.10/','docs/学校对接资料_20261009/',
                   'delivery/docs/','delivery/performance-','delivery/integration_closeout/')
PRIVATE_NAMES={'admin_password','db_root_password','root.cnf','runtime_url','migration_url','db-init.sql',
               'PREPARATION_RECEIPT.json','credentials.json','passwords.json','accounts.json'}
INTERNAL=re.compile(r'C:[/\\]Users|\.codex|Codex|Claude|claude_tmp|合成演示|受限演示|Restricted_Server_Demo',re.I)
IP=re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')


def excluded_reason(name):
    path=PurePosixPath(name); parts=set(path.parts); lower=path.name.lower()
    if path.is_absolute() or '..' in path.parts or '\\' in name:return '路径不安全'
    if name in DEMO_ROOT_FILES or name in EXCLUDED_FILES or name.startswith(EXCLUDED_PREFIXES):return '内部材料或演示入口'
    if parts & PRIVATE_DIRS or any(p.startswith(('.prepare-','.build-context-','.keji-closeout-backup-')) for p in path.parts):return '运行、凭据、附件或临时目录'
    if lower.startswith('.env') and not lower.endswith('.example'):return '私有环境配置'
    if lower.endswith('.inspect.ndjson'):return '工作簿生成过程的检查支持文件'
    if path.suffix.lower() in PRIVATE_SUFFIXES or path.name in PRIVATE_NAMES:return '数据库、密钥或私有文件'
    if path.suffix.lower() in {'.txt','.json','.csv'} and re.search(r'password|credential|secret|test[-_]?accounts?|测试账号|账号口令|密码|口令',lower):return '账号口令或凭据文件'
    if re.search(r'screenshot|截图|截屏',lower):return '测试截图'
    if path.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif'} and not name.startswith(('frontend/assets/','delivery/assets/')):return '截图或非产品图片'
    return None


def package_names(root):
    root=Path(root); names=[n for n in ROOT_FILES if (root/n).is_file() and not excluded_reason(n)]
    for folder in FOLDERS:
        for base,dirs,files in os.walk(root/folder,followlinks=False):
            for leaf in dirs+files:
                path=Path(base)/leaf
                if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                    raise ValueError('打包目录不允许链接: '+path.relative_to(root).as_posix())
            dirs[:]=[d for d in dirs if not excluded_reason((Path(base)/d).relative_to(root).as_posix()+'/')]
            names.extend((Path(base)/n).relative_to(root).as_posix() for n in files
                         if not excluded_reason((Path(base)/n).relative_to(root).as_posix()))
    return sorted(set(names))


def scan_package(root,names):
    root=Path(root); blockers=[]; retained=[]; selected=set(names)
    for name in sorted(names):
        reason=excluded_reason(name)
        if reason:
            blockers.append({'path':name,'reason':reason});continue
        path=root/name
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            blockers.append({'path':name,'reason':'打包文件不允许链接'});continue
        try:
            if path.suffix.lower() in {'.xlsx','.docx','.pptx'}:
                with zipfile.ZipFile(path) as archive:
                    members=[i for i in archive.infolist() if i.filename.endswith('.xml')]
                    if sum(i.file_size for i in members)>64*1024**2:
                        blockers.append({'path':name,'reason':'文档解包扫描超过上限，须人工复核'});continue
                    content='\n'.join(archive.read(i).decode('utf-8') for i in members)
            else:content=path.read_text(encoding='utf-8-sig')
        except UnicodeError:continue
        except zipfile.BadZipFile:
            blockers.append({'path':name,'reason':'办公文档结构损坏，无法扫描'});continue
        program=name.startswith(('backend/','frontend/','deploy/','scripts/','tests/','delivery/')) or name in {'.gitignore','.dockerignore','PACKAGE_MANIFEST.json','release-metadata.json'}
        for number,line in enumerate(content.splitlines(),1):
            internal_matches=list(INTERNAL.finditer(line))
            hits=[m.group(0) for m in internal_matches]
            for match in IP.finditer(line):
                try:address=ipaddress.ip_address(match.group())
                except ValueError:continue
                if address.is_private or address.is_loopback or address.is_unspecified:hits.append(match.group())
            if not hits:continue
            row={'path':name,'line':number,'matches':sorted(set(hits))}
            local_path=any(hit.lower().startswith(('c:/users','c:\\users')) for hit in hits)
            references=[m for m in re.finditer(r'[`"]((?:backend|frontend|deploy|scripts|tests|delivery)/[^`"\r\n]+)[`"]',line)
                        if m.group(1) in selected]
            inventory_reference=(name in {'docs/源代码与资料移交清单.md','docs/交付文件校验清单.json'}
                                 and internal_matches and not local_path and len(hits)==len(internal_matches)
                                 and all(any(m.start(1)<=hit.start() and hit.end()<=m.end(1) for m in references) for hit in internal_matches))
            if program and (not local_path or name.startswith('tests/') or name=='scripts/school_package.py'):
                row['reason']=('回归用例使用的合成测试输入与技术名称，保证测试仍可复现' if name.startswith(('tests/','delivery/tests/')) else
                               '隔离演练的既有代码依赖；正式安装不调用演示初始化' if name.startswith('delivery/') and name!='delivery/R11_BASE_MANIFEST.json' else
                               '程序清单、版本标识、排除规则或本地监听配置；保留原有技术含义')
                retained.append(row)
            elif inventory_reference:
                row['reason']='移交源码文件原名，禁止改名'
                retained.append(row)
            elif all(IP.fullmatch(hit) and (ipaddress.ip_address(hit).is_loopback or ipaddress.ip_address(hit).is_unspecified) for hit in hits):
                row['reason']='本地访问或监听配置说明，不是本机私有地址'
                retained.append(row)
            else:
                row['reason']='学校可见材料含本机路径、内部名称或私有地址';blockers.append(row)
    return {'status':'PASS' if not blockers else 'BLOCKED','files':len(names),'blockers':blockers,'retained_with_reason':retained,
            'school_installation_verified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--staged',action='store_true',help='Check every file already in a package snapshot')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    names=sorted(p.relative_to(args.root).as_posix() for p in args.root.rglob('*') if p.is_file() or p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction())) if args.staged else package_names(args.root)
    report=scan_package(args.root,names)
    payload=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(payload+'\n',encoding='utf-8')
    print(payload)
    return 0 if report['status']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
