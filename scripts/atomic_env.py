#!/usr/bin/env python3
"""Update only requested image keys; never execute .env as shell code."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import stat
import tempfile

IMAGE_KEYS = ('ND_API_IMAGE','ND_FRONTEND_IMAGE')
KEY_LINE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$')
IMAGE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,511}$')


def validate_image(value):
    if not isinstance(value,str) or IMAGE.fullmatch(value) is None or '..' in value.split('/'):
        raise ValueError('invalid image reference')
    return value


def read_env(path):
    """Literal values only; interpolation is rejected for deployment control keys."""
    values = {}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        match = KEY_LINE.fullmatch(line)
        if not match:
            continue
        key,value = match.groups()
        if key in values:
            raise ValueError('duplicate environment key; configuration is ambiguous')
        if value.startswith(('"',"'")):
            quote = value[0]
            end=value.find(quote,1)
            if end<1 or (value[end+1:].strip() and not value[end+1:].lstrip().startswith('#')):
                raise ValueError('invalid quoted environment value')
            value = value[1:end]
        else:
            value = value.split(' #',1)[0].rstrip()
        values[key] = value
    return values


def _signature(s):
    return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_mode,s.st_uid,s.st_gid


def update_images(path, api, frontend):
    p = Path(path)
    values = dict(zip(IMAGE_KEYS, (validate_image(api),validate_image(frontend))))
    fd = os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024*1024:
            raise ValueError('environment must be a small regular non-linked file')
        with os.fdopen(fd,'rb',closefd=False) as stream:
            raw = stream.read()
    finally:
        os.close(fd)
    text = raw.decode('utf-8-sig')
    newline = '\r\n' if '\r\n' in text else '\n'
    seen, lines = set(), []
    for line in text.splitlines():
        match = KEY_LINE.fullmatch(line)
        key = match.group(1) if match else None
        if key in values:
            if key in seen:
                raise ValueError('duplicate image key; refusing ambiguous update')
            seen.add(key)
            lines.append(key+'='+values[key])
        else:
            lines.append(line)
    lines.extend(key+'='+values[key] for key in IMAGE_KEYS if key not in seen)
    payload = (('\ufeff' if raw.startswith(b'\xef\xbb\xbf') else '') + newline.join(lines)+newline).encode('utf-8')
    temp_fd, name = tempfile.mkstemp(prefix='.images-',dir=p.parent)
    try:
        os.fchown(temp_fd,info.st_uid,info.st_gid)
        os.fchmod(temp_fd,stat.S_IMODE(info.st_mode))
        with os.fdopen(temp_fd,'wb',closefd=False) as stream:
            stream.write(payload);stream.flush();os.fsync(temp_fd)
        if _signature(p.lstat()) != _signature(info):
            raise RuntimeError('environment changed during update')
        os.replace(name,p)
        dir_fd = os.open(p.parent,os.O_DIRECTORY)
        try: os.fsync(dir_fd)
        finally: os.close(dir_fd)
    finally:
        os.close(temp_fd)
        if os.path.lexists(name):os.unlink(name)
    return values


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path');parser.add_argument('api');parser.add_argument('frontend')
    args=parser.parse_args()
    try: update_images(args.path,args.api,args.frontend)
    except (ValueError,OSError,RuntimeError,UnicodeError):
        parser.exit(2,'BLOCKED: environment update failed; original values are not printed.\n')
    print('IMAGE_CONFIGURATION_UPDATED')
