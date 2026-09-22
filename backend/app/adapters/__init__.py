"""Deployment adapter contracts and configurable protocol implementations."""
from .contracts import AdapterContractError, normalize_sso_identity
from .http_transport import PinnedHttpsTransport, TransportError
from .sso_configurable import ConfigurableSsoAdapter
from .datahub import ConfigurableDataHubAdapter
from .province import ConfigurableProvinceAdapter

__all__ = [
    'AdapterContractError', 'normalize_sso_identity',
    'PinnedHttpsTransport', 'TransportError',
    'ConfigurableSsoAdapter', 'ConfigurableDataHubAdapter', 'ConfigurableProvinceAdapter',
]
