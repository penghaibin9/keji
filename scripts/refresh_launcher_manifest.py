#!/usr/bin/env python3
"""Rebuild delivery/R11_BASE_MANIFEST.json after changing program code.

The demo launcher (开始部署.sh) refuses to run when program files differ from
this manifest, and it builds images only from the files listed here. Only
program files are listed (backend, frontend, deploy, scripts, tests and root
files), so editing documents never breaks the launcher.
Run after finalising code changes: python3 scripts/refresh_launcher_manifest.py
"""
import hashlib, json, os, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
KEEP = ('backend/', 'frontend/', 'deploy/', 'scripts/', 'tests/')
OUT = ROOT / 'delivery/R11_BASE_MANIFEST.json'
FILES = ('delivery/manage.py', 'delivery/tests/test_deploy_guards.py')
ROOT_FILES = ('.dockerignore', '.gitattributes', '.gitignore', 'README_START_HERE.md',
              'pytest.ini', '先读我_部署与演示.html', '开始部署.sh')
PRIVATE_DIRS = {'__pycache__', '.pytest_cache', '.git', 'node_modules', 'runtime',
                '.runtime', '.venv', 'venv', 'secrets', 'tls', '_claude_tmp',
                '.codex-temp', 'evidence', 'uploads'}
PRIVATE_SUFFIXES = {'.pyc', '.pyo', '.sqlite', '.sqlite3', '.db', '.pem', '.key',
                    '.p12', '.pfx', '.crt', '.zip', '.gz', '.bak'}


def program_names(root):
    names = [n for n in ROOT_FILES if (root / n).is_file()]
    for folder in KEEP:
        for base, dirs, files in os.walk(root / folder, followlinks=False):
            dirs[:] = [d for d in dirs if d not in PRIVATE_DIRS and not d.startswith(('.prepare-', '.build-context-', '.keji-closeout-backup-'))]
            for p in [pathlib.Path(base) / n for n in dirs + files]:
                if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
                    raise ValueError('Program tree contains a link: ' + str(p.relative_to(root)))
            for n in files:
                p = pathlib.Path(base) / n
                if (n.startswith('.env') and not n.endswith('.example')) or p.suffix.lower() in PRIVATE_SUFFIXES:
                    continue
                if n in {'admin_password', 'db_root_password', 'root.cnf', 'runtime_url', 'migration_url', 'db-init.sql', 'PREPARATION_RECEIPT.json'}:
                    continue
                names.append(p.relative_to(root).as_posix())
    return sorted(names)

def main():
    names = program_names(ROOT)
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
