#!/usr/bin/env python3
"""Offline structural check for the fill-in-place three-integration JSON profile.

This does not call the school/province systems and never validates real secrets.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.adapters.common import validate_adapter_config

CODES={'sso','middle','province'}
SECRET_DEFAULTS={'sso':'ND_SSO_SECRET','middle':'ND_MIDDLE_SECRET','province':'ND_PROVINCE_SECRET'}


def main():
    p=argparse.ArgumentParser();p.add_argument('profile');args=p.parse_args()
    path=Path(args.profile)
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(json.dumps({'status':'BLOCKED','reason':'PROFILE_JSON_INVALID'},ensure_ascii=False));return 2
    errors=[];warnings=[]
    if not isinstance(data,dict):
        print(json.dumps({'status':'BLOCKED','reason':'PROFILE_OBJECT_REQUIRED'}));return 2
    if data.get('format')!='YUEKE_R11_THREE_INTEGRATIONS_V2':errors.append('FORMAT_INVALID')
    connections=data.get('connections')
    if not isinstance(connections,dict) or set(connections)!=CODES:errors.append('THREE_CONNECTIONS_REQUIRED')
    else:
        for code in sorted(CODES):
            item=connections.get(code) or {}
            if not isinstance(item,dict) or not isinstance(item.get('config'),dict):
                errors.append(code+':CONFIG_OBJECT_REQUIRED');continue
            config=item['config']
            endpoint=str(config.get('endpoint','')).strip();secret_env=str(config.get('secret_env','')).strip();adapter=config.get('adapter') or {}
            if endpoint:
                u=urlsplit(endpoint)
                if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:errors.append(code+':ENDPOINT_INVALID')
            else:warnings.append(code+':ENDPOINT_WAITING')
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}',secret_env):errors.append(code+':SECRET_ENV_INVALID')
            elif secret_env!=SECRET_DEFAULTS[code]:warnings.append(code+':SECRET_ENV_NONDEFAULT')
            try:validate_adapter_config(adapter)
            except Exception as exc:errors.append(code+':'+getattr(exc,'code','ADAPTER_CONFIG_INVALID'))
            mappings=item.get('mappings')
            if not isinstance(mappings,list):errors.append(code+':MAPPINGS_NOT_LIST')
            if not isinstance(adapter,dict):continue
            if code=='sso' and not str(adapter.get('protocol','')).strip():warnings.append('sso:PROTOCOL_WAITING')
            if code in {'middle','province'} and not isinstance(adapter.get('data_types'),dict):warnings.append(code+':DATA_TYPES_WAITING')
    status='PASS_STRUCTURE_ONLY' if not errors else 'BLOCKED'
    print(json.dumps({'status':status,'errors':errors,'warnings':warnings,
        'external_network_called':False,'secrets_validated':False,
        'next':'补齐学校正式资料后，在系统内逐项执行真实probe；本检查不能作为接口接通证据。'},ensure_ascii=False,indent=2))
    return 0 if not errors else 2

if __name__=='__main__':raise SystemExit(main())
