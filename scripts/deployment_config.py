#!/usr/bin/env python3
"""Generate/verify a private, new-school deployment bundle, without starting services.

Never connects to a school or overwrites existing configuration. Docker file
secrets preserve host permissions: the three application files use UID 10001 and MySQL files use UID 999.
No passwords, database URLs or private key bytes appear in this tool's output.
"""
from __future__ import annotations
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit, unquote, quote
from atomic_env import validate_image, read_env

APP_UID = 10001
DB_UID = 999
APP_SECRET_NAMES = ('runtime_url', 'migration_url', 'admin_password')
ROOT_SECRET_NAMES = ('db_root_password', 'root.cnf', 'db-init.sql')
SECRET_NAMES = APP_SECRET_NAMES + ROOT_SECRET_NAMES
MARKER = '.prepare-incomplete'

class ConfigurationRejected(ValueError):
    """Messages are stable codes, never user-provided secret material."""


def regular_bytes(path, *, maximum=1024*1024):
    path = Path(path)
    for parent in path.parents:
        if parent.is_symlink():
            raise ConfigurationRejected('CONFIG_PARENT_LINK_REFUSED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
            raise ConfigurationRejected('CONFIG_REGULAR_PRIVATE_FILE_REQUIRED')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            return f.read(maximum + 1)
    finally:
        os.close(fd)


def origin_parts(origin):
    if not isinstance(origin, str) or re.search(r'[\s\x00-\x1f\x7f\'"$\\]', origin):
        raise ConfigurationRejected('PUBLIC_ORIGIN_INVALID')
    try:
        u = urlsplit(origin)
        port = u.port or 443
    except ValueError:
        raise ConfigurationRejected('PUBLIC_ORIGIN_INVALID') from None
    if (u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment
            or u.path not in ('', '/') or not 1 <= port <= 65535):
        raise ConfigurationRejected('PUBLIC_ORIGIN_INVALID')
    try:
        ipaddress.ip_address(u.hostname)
    except ValueError:
        if (len(u.hostname)>253 or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p)
            for p in u.hostname.split('.'))):
            raise ConfigurationRejected('PUBLIC_HOST_INVALID')
    return u, port


def _openssl(args):
    try:
        r = subprocess.run(['openssl', *args], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        raise ConfigurationRejected('OPENSSL_UNAVAILABLE') from None
    if r.returncode:
        raise ConfigurationRejected('TLS_VALIDATION_FAILED')
    return r.stdout


def validate_tls(certificate, private_key, hostname):
    # Reading with O_NOFOLLOW first rejects links and oversized/special files.
    regular_bytes(certificate); regular_bytes(private_key, maximum=65536)
    _openssl(['x509', '-in', str(certificate), '-noout', '-checkend', '86400'])
    cert_public = _openssl(['x509', '-in', str(certificate), '-noout', '-pubkey'])
    key_public = _openssl(['pkey', '-in', str(private_key), '-pubout', '-passin', 'pass:'])
    if cert_public.strip() != key_public.strip():
        raise ConfigurationRejected('TLS_KEY_CERTIFICATE_MISMATCH')
    try:
        ipaddress.ip_address(hostname); option, prefix = '-checkip', 'IP'
    except ValueError:
        option, prefix = '-checkhost', 'Hostname'
    result = _openssl(['x509', '-in', str(certificate), '-noout', option, hostname]).decode().strip()
    if result != f'{prefix} {hostname} does match certificate':
        raise ConfigurationRejected('TLS_HOSTNAME_MISMATCH')
    return {'key_pair_checked': True, 'hostname_checked': True, 'expires_after_24h': True,
            'certificate_sha256': hashlib.sha256(regular_bytes(certificate)).hexdigest(),
            'trust_chain_verified': False}


def _write_new(path, data, *, owner=None, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        if owner is not None:
            os.fchown(fd, owner, owner)
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb', closefd=False) as f:
            f.write(data if isinstance(data, bytes) else data.encode()); f.flush(); os.fsync(fd)
    finally:
        os.close(fd)


def _url(user, password):
    return f'mysql+pymysql://{user}:{quote(password, safe="")}@db:3306/nondegree?charset=utf8mb4'


def initial_sql(runtime_password, migration_password):
    # Generated alphabet has no SQL/option-file metacharacters.
    for value in (runtime_password, migration_password):
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', value):
            raise ConfigurationRejected('GENERATED_CREDENTIAL_INVALID')
    return (f"CREATE USER 'nondegree_app'@'%' IDENTIFIED BY '{runtime_password}';\n"
            f"CREATE USER 'nondegree_migration'@'%' IDENTIFIED BY '{migration_password}';\n"
            "GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES, CREATE VIEW, SHOW VIEW, TRIGGER "
            "ON `nondegree`.* TO 'nondegree_migration'@'%';\n")


def verify_private_bundle(root, *, require_ownership=True):
    deploy = Path(root) / 'deploy'
    if os.path.lexists(deploy / MARKER):
        raise ConfigurationRejected('INCOMPLETE_PREPARATION_REFUSED')
    env_bytes = regular_bytes(deploy / '.env', maximum=65536)
    cfg = read_env(deploy / '.env'); u, _ = origin_parts(cfg.get('ND_PUBLIC_ORIGIN', ''))
    if cfg.get('ND_ENV') != 'production' or cfg.get('ND_SECURE_COOKIE') != 'true' or cfg.get('ND_SEED_ENABLED') != 'false':
        raise ConfigurationRejected('PRODUCTION_CONFIG_REQUIRED')
    if not cfg.get('ND_SCHOOL_NAME', '').strip():
        raise ConfigurationRejected('SCHOOL_NAME_REQUIRED')
    if not re.fullmatch(r'nondegree-[a-z0-9][a-z0-9-]{0,39}', cfg.get('ND_PROJECT_NAME', '')):
        raise ConfigurationRejected('ISOLATED_PROJECT_NAME_REQUIRED')
    for name in ('ND_API_IMAGE', 'ND_FRONTEND_IMAGE', 'ND_MYSQL_IMAGE'):
        validate_image(cfg.get(name, ''))
    content = {}
    for name in SECRET_NAMES:
        p = deploy / 'secrets' / name
        content[name] = regular_bytes(p, maximum=65536).decode().strip()
        s = p.stat()
        if stat.S_IMODE(s.st_mode) & 0o077:
            raise ConfigurationRejected('SECRET_EXPOSED_PERMISSIONS')
        if require_ownership:
            expected_uid = APP_UID if name in APP_SECRET_NAMES else DB_UID
            if s.st_uid != expected_uid or not (s.st_mode & stat.S_IRUSR):
                raise ConfigurationRejected('SECRET_CONTAINER_READ_OWNER_MISMATCH')
    credentials = []
    for name, user in (('runtime_url', 'nondegree_app'), ('migration_url', 'nondegree_migration')):
        try:
            parsed = urlsplit(content[name]); port = parsed.port
            password = unquote(parsed.password or '')
        except (ValueError, UnicodeError):
            raise ConfigurationRejected('DATABASE_CREDENTIAL_INVALID') from None
        if (parsed.scheme != 'mysql+pymysql' or parsed.hostname != 'db' or port != 3306 or parsed.path != '/nondegree'
                or unquote(parsed.username or '') != user or parsed.query != 'charset=utf8mb4' or parsed.fragment
                or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', password)):
            raise ConfigurationRejected('DATABASE_IDENTITY_SEPARATION_REQUIRED')
        credentials.append(password)
    root_password = content['db_root_password']
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', root_password):
        raise ConfigurationRejected('ROOT_CREDENTIAL_INVALID')
    if len(set([root_password, *credentials, content['admin_password']])) != 4 or len(content['admin_password']) < 16:
        raise ConfigurationRejected('CREDENTIAL_REUSE_OR_WEAK_PASSWORD')
    expected_cnf = f'[client]\nuser=root\npassword={root_password}\nprotocol=socket'
    if content['root.cnf'] != expected_cnf or content['db-init.sql'] != initial_sql(*credentials).strip():
        raise ConfigurationRejected('DATABASE_BOOTSTRAP_CREDENTIAL_MISMATCH')
    if stat.S_IMODE((deploy / '.env').stat().st_mode) & 0o077:
        raise ConfigurationRejected('ENVIRONMENT_EXPOSED_PERMISSIONS')
    tls = validate_tls(deploy / 'tls/fullchain.pem', deploy / 'tls/privkey.pem', u.hostname)
    if require_ownership:
        for name in ('tls','tls/fullchain.pem','tls/privkey.pem'):
            info=(deploy/name).stat()
            if info.st_uid!=APP_UID or not (info.st_mode & stat.S_IRUSR) or (name=='tls' and not info.st_mode & stat.S_IXUSR):
                raise ConfigurationRejected('TLS_CONTAINER_READ_OWNER_MISMATCH')
        if (deploy/'tls/privkey.pem').stat().st_mode & 0o007:
            raise ConfigurationRejected('TLS_PRIVATE_KEY_EXPOSED')
    return {'status': 'PRIVATE_CONFIGURATION_VERIFIED', 'separated_accounts': True,
            'application_secret_owner_checked': require_ownership, 'tls': tls,
            'database_contacted': False, 'production_deployment_approved': False}


def prepare(root, *, school_name, origin, api_image, frontend_image, mysql_image, certificate, private_key):
    if os.geteuid() != 0:
        raise ConfigurationRejected('ADMINISTRATOR_REQUIRED_FOR_FILE_OWNERSHIP')
    root = Path(os.path.abspath(root)); deploy = root / 'deploy'
    for parent in (root, *root.parents, deploy):
        if parent.is_symlink():
            raise ConfigurationRejected('CONFIG_PARENT_LINK_REFUSED')
    if not deploy.is_dir() or not (deploy/'compose.yml').is_file():
        raise ConfigurationRejected('EXTRACTED_SOURCE_ROOT_REQUIRED')
    for name in ('.env', 'secrets', 'tls', MARKER):
        if os.path.lexists(deploy/name):
            raise ConfigurationRejected('EXISTING_CONFIGURATION_NEVER_OVERWRITTEN')
    if (root/'runtime').is_symlink():
        raise ConfigurationRejected('EXISTING_SCHOOL_DATA_REFUSED')
    for name in ('mysql', 'files'):
        p = root/'runtime'/name
        if os.path.lexists(p) and (p.is_symlink() or not p.is_dir() or any(p.iterdir())):
            raise ConfigurationRejected('EXISTING_SCHOOL_DATA_REFUSED')
    if not isinstance(school_name, str) or not 1 <= len(school_name.strip()) <= 120 or re.search(r'[\x00-\x1f\x7f\'"$\\]', school_name):
        raise ConfigurationRejected('SCHOOL_NAME_INVALID')
    u, port = origin_parts(origin)
    for image in (api_image, frontend_image, mysql_image):
        validate_image(image)
        if ':' not in image and '@sha256:' not in image:
            raise ConfigurationRejected('EXPLICIT_IMAGE_VERSION_REQUIRED')
    cert_data = regular_bytes(certificate); key_data = regular_bytes(private_key, maximum=65536)
    tls = validate_tls(certificate, private_key, u.hostname)
    # A retained latch after interruption prevents treating a partial bundle as usable.
    _write_new(deploy/MARKER, json.dumps({'status':'PREPARING','contains_secret_values':False}))
    stage = Path(tempfile.mkdtemp(prefix='.prepare-', dir=deploy)); stage.chmod(0o700)
    try:
        (stage/'secrets').mkdir(mode=0o700); (stage/'tls').mkdir(mode=0o750)
        root_password, app_password, migration_password, admin_password = [secrets.token_urlsafe(36) for _ in range(4)]
        data = {'db_root_password':root_password, 'root.cnf':f'[client]\nuser=root\npassword={root_password}\nprotocol=socket\n',
                'runtime_url':_url('nondegree_app', app_password), 'migration_url':_url('nondegree_migration', migration_password),
                'admin_password':admin_password, 'db-init.sql':initial_sql(app_password, migration_password)}
        for name, value in data.items():
            _write_new(stage/'secrets'/name, value+'\n', owner=APP_UID if name in APP_SECRET_NAMES else DB_UID, mode=0o400)
        _write_new(stage/'tls/fullchain.pem', cert_data, owner=APP_UID, mode=0o400)
        _write_new(stage/'tls/privkey.pem', key_data, owner=APP_UID, mode=0o400)
        os.chown(stage/'tls', APP_UID, APP_UID)
        project = 'nondegree-'+secrets.token_hex(8)
        env = '\n'.join(['# Private school-specific configuration. Never commit or distribute.',
            'ND_ENV=production', f'ND_SCHOOL_NAME="{school_name.strip()}"', f'ND_PUBLIC_ORIGIN={origin.rstrip("/")}',
            f'ND_ALLOWED_HOSTS={u.hostname},localhost,127.0.0.1', f'ND_PROJECT_NAME={project}',
            f'ND_API_IMAGE={api_image}', f'ND_FRONTEND_IMAGE={frontend_image}', f'ND_MYSQL_IMAGE={mysql_image}',
            f'ND_HTTPS_PORT={port}', 'ND_BIND_IP=0.0.0.0','ND_SECURE_COOKIE=true','ND_SEED_ENABLED=false',
            'ND_RELEASE_GUARD=true', 'ND_ADAPTER_MODULES=', ''])
        _write_new(stage/'.env', env)
        for name in ('secrets', 'tls', '.env'):
            if os.path.lexists(deploy/name):
                raise ConfigurationRejected('CONCURRENT_CONFIGURATION_REFUSED')
            os.rename(stage/name, deploy/name)
        (deploy/MARKER).unlink()
        try:
            report = verify_private_bundle(root)
        except Exception:
            _write_new(deploy/MARKER, '{"status":"VERIFY_FAILED"}')
            raise
        report.update(project=project, admin_secret='deploy/secrets/admin_password',
                      service_started=False, tls=tls)
        _write_new(deploy/'PREPARATION_RECEIPT.json', json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        return report
    finally:
        shutil.rmtree(stage)


def main():
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare'); p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    for key in ('school-name','origin','api-image','frontend-image','mysql-image','certificate','private-key'):
        p.add_argument('--'+key,required=True)
    p.add_argument('--new-school-only',action='store_true',required=True)
    v=sub.add_parser('verify');v.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    a=ap.parse_args()
    try:
        result=verify_private_bundle(a.root) if a.action=='verify' else prepare(a.root,**{key:getattr(a,key) for key in
            ('school_name','origin','api_image','frontend_image','mysql_image','certificate','private_key')})
    except (ValueError, OSError, UnicodeError) as exc:
        code=str(exc) if isinstance(exc,ConfigurationRejected) else 'PRIVATE_CONFIGURATION_REJECTED'
        ap.exit(2,'BLOCKED: '+code+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
