#!/usr/bin/env python3
"""Hash every regular backup file; reject traversal, links and unknown files."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def inventory(root):
    root=Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError('invalid backup root')
    result={}
    for directory,dirs,files in os.walk(root,followlinks=False):
        for name in dirs+files:
            p=Path(directory)/name;s=p.lstat()
            if stat.S_ISLNK(s.st_mode):raise ValueError('links are forbidden in backup')
            if p.is_dir():continue
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:raise ValueError('special or linked file')
            relative=p.relative_to(root).as_posix()
            if relative=='manifest.json':continue
            if '\\' in relative:raise ValueError('nonportable backup path')
            result[relative]={'sha256':sha256(p),'bytes':s.st_size}
    return result


def create(root):
    root=Path(root)
    if (root/'manifest.json').exists():raise ValueError('manifest already exists')
    files=inventory(root)
    if 'database.sql.gz' not in files or files['database.sql.gz']['bytes']==0:
        raise ValueError('database dump missing')
    data={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(), 'files':files}
    fd,name=tempfile.mkstemp(prefix='.manifest-',dir=root)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,root/'manifest.json')
        os.chmod(root/'manifest.json',0o600)
    finally:
        if os.path.lexists(name):os.unlink(name)
    return verify(root)


def verify(root):
    root=Path(root)
    p=root/'manifest.json'
    if p.is_symlink() or not p.is_file() or p.stat().st_size>16*1024*1024:
        raise ValueError('manifest missing or invalid')
    data=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('schema_version')!=1 or not isinstance(data.get('files'),dict):
        raise ValueError('unsupported manifest')
    expected=data['files']
    for name,entry in expected.items():
        q=PurePosixPath(name)
        if not name or '\\' in name or q.is_absolute() or any(v in {'.','..',''} for v in name.split('/')) or not isinstance(entry,dict):
            raise ValueError('unsafe manifest path')
        if set(entry)!={'sha256','bytes'} or not isinstance(entry['sha256'],str) or type(entry['bytes']) is not int or entry['bytes']<0:
            raise ValueError('invalid manifest entry')
    current=inventory(root)
    if current != expected or 'database.sql.gz' not in current:
        raise ValueError('backup manifest mismatch')
    return {'files':len(current),'manifest_sha256':sha256(p)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['create','verify']);p.add_argument('directory');a=p.parse_args()
    try: result=(create if a.action=='create' else verify)(a.directory)
    except (ValueError,OSError,KeyError,TypeError):p.exit(2,'BACKUP_MANIFEST_REJECTED\n')
    print(json.dumps(result))
