"""Configurable outbound adapter for 湘培直通车 / province platform."""
from __future__ import annotations

from .contracts import AdapterContractError
from .common import parse_credential, path_get, matches_value
import re
from .rest import ConfigurableRestBase


class ConfigurableProvinceAdapter(ConfigurableRestBase):
    adapter_id = 'yueke.province.configurable.v2'

    def probe(self, *, config, credential, timeout_seconds):
        return self._probe(config=config, credential=credential, timeout_seconds=timeout_seconds)

    def send(self, *, data_type, payload, idempotency_key, config, credential, timeout_seconds):
        if not isinstance(payload, dict) or not idempotency_key:
            raise AdapterContractError('PROVINCE_SEND_INVALID')
        adapter = self._adapter_config(config)
        data_types = adapter.get('data_types')
        if not isinstance(data_types, dict) or data_type not in data_types:
            raise AdapterContractError('PROVINCE_DATA_TYPE_NOT_CONFIGURED')
        spec = data_types[data_type]
        if not isinstance(spec, dict):
            raise AdapterContractError('PROVINCE_DATA_TYPE_NOT_CONFIGURED')
        request_spec = spec.get('request')
        response_spec = spec.get('response') or {}
        credentials = parse_credential(credential)
        context = self._request_context(adapter, {'data_type': data_type, 'payload': payload, 'idempotency_key': idempotency_key})
        response = self._request_json(endpoint=str(config.get('endpoint', '')).strip(), spec=request_spec,
                                      context=context, credentials=credentials, timeout_seconds=timeout_seconds)
        if not isinstance(response_spec, dict):
            raise AdapterContractError('PROVINCE_RESPONSE_SPEC_INVALID')
        accepted_path = str(response_spec.get('accepted_path', '')).strip()
        def rejected():
            raw=path_get(response,str(response_spec.get('code_path','')),None) if response_spec.get('code_path') else None
            known=response_spec.get('error_codes',[])
            # Persist only school-documented codes, never arbitrary response text.
            error=AdapterContractError('PROVINCE_UPSTREAM_REJECTED')
            if isinstance(known,list) and type(raw) in (str,int) and str(raw) in known and re.fullmatch(r'[A-Za-z0-9_.-]{1,40}',str(raw)):
                error.upstream_code=str(raw)
            return error
        if accepted_path:
            accepted = path_get(response, accepted_path)
            accepted_values = response_spec.get('accepted_values', [True, 1, '1', 'SUCCESS', 'OK'])
            if not matches_value(accepted,accepted_values):
                raise rejected()
        elif response_spec.get('success_path'):
            actual = path_get(response, str(response_spec['success_path']))
            allowed = response_spec.get('success_values', [0, '0', 'SUCCESS', 'OK'])
            if not matches_value(actual,allowed):
                raise rejected()
        else:
            raise AdapterContractError('PROVINCE_ACCEPTANCE_RULE_MISSING')
        code = 'ACK'
        code_path = str(response_spec.get('code_path', '')).strip()
        if code_path:
            code = str(path_get(response, code_path, 'ACK'))[:40]
        receipt_id = ''
        receipt_path = str(response_spec.get('receipt_id_path', '')).strip()
        if receipt_path:
            receipt_id = str(path_get(response, receipt_path, ''))[:128]
        result = {'accepted': True, 'code': code or 'ACK'}
        if receipt_id:
            result['receipt_id'] = receipt_id
        return result
