#!/usr/bin/env python3
"""HTTPS/asset/readiness smoke while the maintenance latch is still active.
This does not replace authenticated business-flow or school browser acceptance.
"""
from __future__ import annotations
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

class Assets(HTMLParser):
    def __init__(self):super().__init__();self.paths=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script' and a.get('src'):self.paths.append(a['src'])
        if tag=='link' and a.get('rel')=='stylesheet' and a.get('href'):self.paths.append(a['href'])


def run_smoke(origin,ca_file=None):
    base=urlsplit(origin)
    if base.scheme!='https' or not base.hostname or base.username or base.password or base.query or base.fragment or base.path not in {'','/'}:
        raise ValueError('ND_PUBLIC_ORIGIN must be an HTTPS origin')
    context=ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
    opener=build_opener(HTTPSHandler(context=context),NoRedirect())
    def get(path):
        url=urljoin(origin.rstrip('/')+'/',path)
        target=urlsplit(url)
        if (target.scheme,target.netloc)!=(base.scheme,base.netloc):raise ValueError('cross-origin asset rejected')
        try:
            with opener.open(Request(url,headers={'Cache-Control':'no-cache'}),timeout=10) as r:
                data=r.read(2*1024*1024+1)
                if len(data)>2*1024*1024:raise ValueError('smoke response exceeds limit')
                return r.status,data
        except HTTPError as e:
            return e.code,e.read(8192)
    status,html=get('/')
    if status!=200:raise ValueError('frontend is not ready')
    parser=Assets();parser.feed(html.decode('utf-8'))
    if not parser.paths or not any(urlsplit(x).path.endswith('.js') for x in parser.paths):raise ValueError('frontend application entry missing')
    seen=set();queue=[urljoin(origin+'/',p) for p in parser.paths]
    while queue:
        path=queue.pop(0)
        if path in seen:continue
        seen.add(path)
        if len(seen)>80:raise ValueError('too many smoke assets')
        status,body=get(path)
        if status!=200 or not body or re.match(br'\s*<(?:!doctype\s+html|html|head|body)(?:\s|>)',body,re.I):raise ValueError('asset missing or HTML fallback')
        if urlsplit(path).path.endswith('.js'):
            for rel in re.findall(r'''(?:from\s*|import\s*)['"](\.{1,2}/[^'"]+)['"]''',body.decode('utf-8')):
                queue.append(urljoin(path,rel))
    status,data=get('/api/health');health=json.loads(data)
    if status!=200 or health.get('status')!='ok' or health.get('accepting_requests') is not False or health.get('maintenance')!='ACTIVE':
        raise ValueError('readiness or maintenance contract mismatch')
    for section in ('database','migration','initialization'):
        if health.get(section,{}).get('status')!='ok':raise ValueError('not initialized')
    status,data=get('/api/records')
    if status!=503 or json.loads(data).get('code')!='MAINTENANCE':raise ValueError('public business request is not blocked during maintenance')
    return {'status':'PASS','scope':'HTTPS_ASSETS_AND_READINESS_ONLY','asset_count':len(seen),'business_e2e':False}
