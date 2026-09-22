"""Register the prebuilt configurable adapters for a school deployment.

Only endpoints and secret *references* are read here. Real secret values remain
in server environment variables and never enter database/browser configuration.
"""
from __future__ import annotations
import os
from app.adapters import ConfigurableSsoAdapter, ConfigurableDataHubAdapter, ConfigurableProvinceAdapter


def register(registry):
    specs = [
        ('sso', ConfigurableSsoAdapter(), 'ND_SSO_ENDPOINT', 'ND_SSO_SECRET'),
        ('middle', ConfigurableDataHubAdapter(), 'ND_MIDDLE_ENDPOINT', 'ND_MIDDLE_SECRET'),
        ('province', ConfigurableProvinceAdapter(), 'ND_PROVINCE_ENDPOINT', 'ND_PROVINCE_SECRET'),
    ]
    for code, adapter, endpoint_name, secret_name in specs:
        endpoint = os.environ.get(endpoint_name, '').strip()
        if not endpoint:
            continue
        registry.register_production(code, adapter, endpoint=endpoint, credential_env=secret_name)
