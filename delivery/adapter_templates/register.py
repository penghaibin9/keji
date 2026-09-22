"""兼容注册入口。

生产环境推荐直接设置：ND_ADAPTER_MODULES=school_adapters.register。
本文件保留给旧部署脚本兼容，行为与正式注册模块一致。
"""
import os
from .hnkj_sso import HnkjSsoAdapter
from .hnkj_datahub import HnkjDataHubAdapter
from .xiangpei import XiangpeiAdapter


def register(registry):
    specs = [
        ('sso', HnkjSsoAdapter(), 'ND_SSO_ENDPOINT', 'ND_SSO_SECRET'),
        ('middle', HnkjDataHubAdapter(), 'ND_MIDDLE_ENDPOINT', 'ND_MIDDLE_SECRET'),
        ('province', XiangpeiAdapter(), 'ND_PROVINCE_ENDPOINT', 'ND_PROVINCE_SECRET'),
    ]
    for code, adapter, endpoint_env, credential_env in specs:
        endpoint = os.environ.get(endpoint_env, '').strip()
        if not endpoint:
            continue
        registry.register_production(code, adapter, endpoint=endpoint, credential_env=credential_env)
