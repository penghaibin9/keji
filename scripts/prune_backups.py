#!/usr/bin/env python3
"""Prune completed deployment backups; run separately from the backup operation."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat

ROOT=Path(__file__).resolve().parents[1]
STAMP=re.compile(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}')


def regular_entry(path,directory=False):
    info=path.lstat()
    if getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):return False
    return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink==1


def safe_backup(path):
    if not regular_entry(path,True):return False
    receipt=path.with_name(path.name+'.receipt.json')
    if os.path.lexists(receipt) and not regular_entry(receipt):return False
    def failed_scan(error):raise error
    for directory,dirs,files in os.walk(path,followlinks=False,onerror=failed_scan):
        if any(not regular_entry(Path(directory)/name,True) for name in dirs):return False
        if any(not regular_entry(Path(directory)/name) for name in files):return False
    return True


def prune(root=ROOT,keep=7,dry_run=False):
    if keep<1:raise ValueError('keep must be at least 1')
    base=Path(os.path.abspath(root))/'runtime/backups'
    result={'keep':keep,'dry_run':dry_run,'kept':[],'deleted':[],'would_delete':[],'skipped':[]}
    # Do not create directories during a dry run or follow a linked ancestor.
    for component in (*reversed(base.parents),base):
        if not os.path.lexists(component):return result
        if not regular_entry(component,True):raise ValueError('unsafe backup directory')
    candidates=[]
    for path in sorted(base.iterdir()):
        if STAMP.fullmatch(path.name) and safe_backup(path):candidates.append(path)
        elif not (path.name.endswith('.receipt.json') and STAMP.fullmatch(path.name[:-13])):
            result['skipped'].append(path.name)
    result['kept']=[p.name for p in candidates[-keep:]]
    for path in candidates[:-keep]:
        if dry_run:result['would_delete'].append(path.name);continue
        if path.resolve()!=base/path.name or not safe_backup(path):
            result['skipped'].append(path.name);continue
        shutil.rmtree(path)
        receipt=path.with_name(path.name+'.receipt.json')
        if os.path.lexists(receipt) and regular_entry(receipt):receipt.unlink()
        result['deleted'].append(path.name)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--keep',type=int,default=7);p.add_argument('--dry-run',action='store_true');a=p.parse_args(argv)
    if a.keep<1:p.error('--keep must be at least 1')
    try:result=prune(ROOT,a.keep,a.dry_run)
    except (OSError,ValueError):
        print(json.dumps({'status':'BLOCKED','error':'backup pruning failed'}));return 2
    print(json.dumps(result,ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
