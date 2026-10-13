"""真实来源 IP：学校的反向代理会把所有用户都转发成同一个地址，登录限流按 IP 计数，会把全校当成一个人。

默认关闭。只有直连方（nginx 看到的上一跳）在 ND_TRUSTED_PROXIES 里时，才采用代理转发过来的客户端链
（nginx 把收到的 X-Forwarded-For 原样放进 X-Client-Chain）。从右往左跳过自己信任的代理，
第一个不在信任列表里的地址就是真实来源；客户端自己写在最左边的内容不会被采用。
"""
from __future__ import annotations
import ipaddress
from fastapi import Request

CHAIN_HEADER = 'x-client-chain'


def parse_networks(text: str):
    """'10.255.1.34, 10.0.0.0/8' -> list of ip_network; raises ValueError on a malformed entry."""
    networks = []
    for part in (text or '').split(','):
        part = part.strip()
        if part:
            networks.append(ipaddress.ip_network(part, strict=False))
    return networks


def _inside(address: str, networks) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in n for n in networks)


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else 'unknown'
    networks = getattr(request.app.state.settings, 'trusted_proxy_networks', [])
    if not networks or not _inside(peer, networks):
        return peer
    chain = [x.strip() for x in request.headers.get(CHAIN_HEADER, '').split(',') if x.strip()]
    for address in reversed(chain):
        try:
            ipaddress.ip_address(address)
        except ValueError:
            return peer          # 链里有无法识别的内容：不冒险采用，回到直连地址
        if not _inside(address, networks):
            return address
    return peer
