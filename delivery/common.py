"""Local safety primitives. Digests detect changes; they are not signatures."""
from __future__ import annotations
import hashlib, json, os, stat, subprocess, tempfile
from pathlib import Path

class Blocked(RuntimeError): pass

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def secure_json(path, data, *, exclusive=False):
    path=Path(path)
    if path.is_symlink(): raise Blocked('SYMLINK_OUTPUT_REFUSED')
    if exclusive:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'w') as f: json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        return
    fd,name=tempfile.mkstemp(prefix='.write-',dir=path.parent)
    try:
        # Windows browser reports inherit the operator's private-directory ACL.
        # Unix deployment secrets additionally get an explicit 0600 mode.
        if hasattr(os,'fchmod'):os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f: json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def load_private(path):
    path=Path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>16*1024*1024 or s.st_mode&0o077:
            raise Blocked('PRIVATE_REGULAR_FILE_REQUIRED')
        with os.fdopen(fd,'r',closefd=False) as f:return json.load(f)
    finally:os.close(fd)

def safe_path(path, *, must_abs=True):
    p=Path(path)
    if (must_abs and not p.is_absolute()) or '..' in p.parts:raise Blocked('ABSOLUTE_NONTRAVERSING_PATH_REQUIRED')
    for x in (p,*p.parents):
        if os.path.lexists(x) and (x.is_symlink() or not x.is_dir()):raise Blocked('PATH_COMPONENT_NOT_REAL_DIRECTORY')
    return p

def command(args, *, timeout=90, cwd=None, log=None):
    env={k:v for k,v in os.environ.items() if not k.startswith(('ND_','COMPOSE_')) and k not in ('DOCKER_HOST','DOCKER_CONTEXT')}
    # Do not leak command output (which might contain application data) into chat or shell history.
    try:
        r=subprocess.run([str(a) for a in args],cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as e:raise Blocked('COMMAND_UNAVAILABLE_OR_TIMEOUT') from e
    if log:
        p=Path(log);fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'ab') as f:f.write(r.stdout)
    if r.returncode:raise Blocked('COMMAND_FAILED_SEE_PRIVATE_LOG' if log else 'COMMAND_FAILED_OUTPUT_SUPPRESSED')
    return r.stdout

def verify_baseline(root):
    root=Path(root);m=json.loads((root/'delivery/R11_BASE_MANIFEST.json').read_text())
    for name,expected in m['files'].items():
        p=root/name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise Blocked('R11_BASELINE_CHANGED: '+name)
    return m['input_zip_sha256']
