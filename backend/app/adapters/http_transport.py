"""Pinned HTTPS transport shared by production adapters.

HTTPS only, same-origin relative requests, verified system TLS, no redirects,
bounded payloads/responses and no persistence of credentials/raw upstream bodies.
"""
from __future__ import annotations

import json
import ssl
import os
import socket
import ipaddress
import http.client
import uuid
from urllib.parse import urlsplit, urljoin, urlencode, unquote
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError


class TransportError(RuntimeError):
    def __init__(self, code: str, status: int | None = None):
        super().__init__(code)
        self.code = code
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _PinnedConnection(http.client.HTTPSConnection):
    def connect(self):
        # Resolve once, check every address, then connect to those exact addresses.
        # Private school networks require an explicit SERVER-side hostname allowlist.
        allowed={x.strip().lower() for x in os.environ.get('ND_INTEGRATION_PRIVATE_HOSTS','').split(',') if x.strip()}
        addresses=socket.getaddrinfo(self.host,self.port,type=socket.SOCK_STREAM)
        if not addresses:raise TransportError('UPSTREAM_DNS_EMPTY')
        for _,_,_,_,address in addresses:
            ip=ipaddress.ip_address(address[0])
            if not ip.is_global and (self.host.lower() not in allowed or ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast):
                raise TransportError('UPSTREAM_ADDRESS_FORBIDDEN')
        last=None
        for family,socktype,proto,_,address in addresses:
            sock=socket.socket(family,socktype,proto)
            try:
                sock.settimeout(self.timeout);sock.connect(address)
                self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
                return
            except OSError as exc:
                sock.close();last=exc
        raise TransportError('UPSTREAM_TRANSPORT_ERROR') from None


class _PinnedHandler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PinnedConnection,req,context=self._context)


class PinnedHttpsTransport:
    """Small stdlib transport so adapters do not each reinvent SSRF/TLS guards."""
    def __init__(self, base_url: str, *, max_response_bytes: int = 2 * 1024 * 1024):
        raw = str(base_url or '').strip()
        parsed = urlsplit(raw)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError('INVALID_PINNED_HTTPS_BASE')
        self.base_url = raw.rstrip('/') + '/'
        self.origin = (parsed.scheme, parsed.hostname.lower(), parsed.port or 443)
        self.max_response_bytes = int(max_response_bytes)
        if not 1024 <= self.max_response_bytes <= 10 * 1024 * 1024:
            raise ValueError('INVALID_RESPONSE_LIMIT')
        context = ssl.create_default_context()
        self._opener = build_opener(ProxyHandler({}), _NoRedirect(), _PinnedHandler(context=context))

    def target(self, relative_path: str) -> str:
        path = str(relative_path or '').strip()
        if not path or path.startswith('//') or '://' in path or '\\' in path or any(ord(c)<32 for c in path):
            raise ValueError('RELATIVE_PATH_REQUIRED')
        decoded=urlsplit(path).path
        for _ in range(4):
            decoded=unquote(decoded)
            if '\\' in decoded or '..' in decoded.split('/') or any(ord(c)<32 for c in decoded):
                raise ValueError('BASE_PATH_ESCAPE_FORBIDDEN')
        if '%' in decoded:raise ValueError('PATH_ENCODING_INVALID')
        target = urljoin(self.base_url, path.lstrip('/'))
        parsed = urlsplit(target)
        origin = (parsed.scheme, (parsed.hostname or '').lower(), parsed.port or 443)
        if origin != self.origin or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('CROSS_ORIGIN_TARGET_FORBIDDEN')
        if not parsed.path.startswith(urlsplit(self.base_url).path):
            raise ValueError('BASE_PATH_ESCAPE_FORBIDDEN')
        return target

    def request_bytes(self, method: str, relative_path: str, *, headers: dict | None = None,
                      body: bytes | None = None, timeout_seconds: int = 10,
                      allowed_content_types: set[str] | None = None) -> tuple[int, str, bytes]:
        verb = str(method or '').upper()
        if verb not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
            raise ValueError('HTTP_METHOD_FORBIDDEN')
        if not 1 <= int(timeout_seconds) <= 30:
            raise ValueError('INVALID_TIMEOUT')
        if body is not None and (not isinstance(body, bytes) or len(body) > 2 * 1024 * 1024):
            raise ValueError('REQUEST_TOO_LARGE')
        request_headers = {}
        for key, value in (headers or {}).items():
            k, v = str(key).strip(), str(value).strip()
            if not k or '\r' in k or '\n' in k or '\r' in v or '\n' in v or k.lower() in {'host','proxy-authorization','proxy-connection','connection','transfer-encoding','content-length'}:
                raise ValueError('INVALID_HEADER')
            request_headers[k] = v
        request_headers.setdefault('X-Request-ID',uuid.uuid4().hex)
        req = Request(self.target(relative_path), data=body, headers=request_headers, method=verb)
        try:
            with self._opener.open(req, timeout=int(timeout_seconds)) as response:
                status = int(getattr(response, 'status', 200))
                content_type = (response.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
                if allowed_content_types is not None:
                    good = content_type in allowed_content_types or any(
                        item.startswith('*+') and content_type.endswith(item[1:]) for item in allowed_content_types
                    )
                    if not good:
                        raise TransportError('UPSTREAM_CONTENT_TYPE_INVALID', status)
                raw = response.read(self.max_response_bytes + 1)
                if len(raw) > self.max_response_bytes:
                    raise TransportError('UPSTREAM_RESPONSE_TOO_LARGE', status)
                return status, content_type, raw
        except HTTPError as exc:
            raise TransportError('UPSTREAM_HTTP_ERROR', getattr(exc, 'code', None)) from None
        except (URLError, TimeoutError, OSError, ssl.SSLError):
            raise TransportError('UPSTREAM_TRANSPORT_ERROR') from None

    def request_json(self, method: str, relative_path: str, *, headers: dict | None = None,
                     payload: dict | list | None = None, timeout_seconds: int = 10) -> dict | list:
        request_headers = {'Accept': 'application/json', **(headers or {})}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            request_headers.setdefault('Content-Type', 'application/json; charset=utf-8')
        _, _, raw = self.request_bytes(method, relative_path, headers=request_headers, body=body,
                                       timeout_seconds=timeout_seconds,
                                       allowed_content_types={'application/json', '*+json'})
        try:
            value = json.loads(raw.decode('utf-8'))
        except Exception:
            raise TransportError('UPSTREAM_JSON_INVALID') from None
        if not isinstance(value, (dict, list)):
            raise TransportError('UPSTREAM_JSON_SHAPE_INVALID')
        return value

    def request_form_json(self, relative_path: str, *, form: dict, headers: dict | None = None,
                          timeout_seconds: int = 10) -> dict | list:
        pairs = []
        for key, value in (form or {}).items():
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                raise ValueError('FORM_VALUE_INVALID')
            pairs.append((str(key), str(value)))
        body = urlencode(pairs).encode('utf-8')
        request_headers = {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded', **(headers or {})}
        _, _, raw = self.request_bytes('POST', relative_path, headers=request_headers, body=body,
                                       timeout_seconds=timeout_seconds,
                                       allowed_content_types={'application/json', '*+json'})
        try:
            value = json.loads(raw.decode('utf-8'))
        except Exception:
            raise TransportError('UPSTREAM_JSON_INVALID') from None
        if not isinstance(value, (dict, list)):
            raise TransportError('UPSTREAM_JSON_SHAPE_INVALID')
        return value

    def request_text(self, method: str, relative_path: str, *, headers: dict | None = None,
                     form: dict | None = None, timeout_seconds: int = 10,
                     allowed_content_types: set[str] | None = None) -> str:
        body = None
        request_headers = dict(headers or {})
        if form is not None:
            body = urlencode([(str(k), str(v)) for k, v in form.items() if v is not None]).encode('utf-8')
            request_headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        _, _, raw = self.request_bytes(method, relative_path, headers=request_headers, body=body,
                                       timeout_seconds=timeout_seconds, allowed_content_types=allowed_content_types)
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            raise TransportError('UPSTREAM_TEXT_INVALID') from None
