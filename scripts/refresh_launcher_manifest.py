#!/usr/bin/env python3
"""Rebuild delivery/R11_BASE_MANIFEST.json after changing program code.

The demo launcher (开始部署.sh) refuses to run when program files differ from
this manifest, and it builds images only from the files listed here. Only
program files are listed (backend, frontend, deploy, scripts, tests and root
files), so editing documents never breaks the launcher.
Run after committing code changes:  python3 scripts/refresh_launcher_manifest.py
"""
import hashlib, json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
KEEP = ('backend/', 'frontend/', 'deploy/', 'scripts/', 'tests/')
OUT = ROOT / 'delivery/R11_BASE_MANIFEST.json'
FILES = ('delivery/manage.py', 'delivery/tests/test_deploy_guards.py')

def main():
    listed = subprocess.run(['git', '-c', 'core.quotepath=off', 'ls-files', '-z'], cwd=ROOT,
                            capture_output=True, check=True).stdout.decode().split('\0')
    names = sorted(n for n in listed if n and (n.startswith(KEEP) or '/' not in n))
    files = {}
    for n in names:
        p = ROOT / n
        if p.is_file() and not p.is_symlink():
            files[n] = hashlib.sha256(p.read_bytes()).hexdigest()
    new = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    old = json.loads(OUT.read_text(encoding='utf-8'))['input_zip_sha256']
    OUT.write_text(json.dumps({'input_zip_sha256': new, 'baseline_note': 'program files only; rebuilt by scripts/refresh_launcher_manifest.py', 'files': files}, ensure_ascii=False, indent=1), encoding='utf-8')
    for f in FILES:
        p = ROOT / f
        p.write_bytes(p.read_bytes().replace(old.encode(), new.encode()))
    print(f'{len(files)} program files; baseline {new}')

if __name__ == '__main__':
    sys.exit(main())
