"""Configurable school data-hub REST/JSON adapter.

The school-specific URL paths, authentication details and JSON field locations
live in ``Connection.config['adapter']``. Secrets stay in the server environment.
"""
from __future__ import annotations

from .contracts import AdapterContractError
from .common import parse_credential, path_get, normalized_bool, matches_value
from .rest import ConfigurableRestBase


class ConfigurableDataHubAdapter(ConfigurableRestBase):
    adapter_id = 'yueke.datahub.configurable.v2'

    def probe(self, *, config, credential, timeout_seconds):
        return self._probe(config=config, credential=credential, timeout_seconds=timeout_seconds)

    def pull(self, *, data_type, mode, cursor, limit, config, credential, timeout_seconds):
        if mode not in {'FULL', 'INCREMENTAL'} or type(limit) is not int or not 1 <= limit <= 1000:
            raise AdapterContractError('PULL_REQUEST_INVALID')
        adapter = self._adapter_config(config)
        data_types = adapter.get('data_types')
        if not isinstance(data_types, dict) or data_type not in data_types:
            raise AdapterContractError('PULL_DATA_TYPE_NOT_CONFIGURED')
        spec = data_types[data_type]
        if not isinstance(spec, dict):
            raise AdapterContractError('PULL_DATA_TYPE_NOT_CONFIGURED')
        request_spec = spec.get('request')
        response_spec = spec.get('response') or {}
        credentials = parse_credential(credential)
        paging=spec.get('pagination') or {}
        page_size=paging.get('page_size',limit);max_pages=paging.get('max_pages',20)
        if type(page_size) is not int or not 1<=page_size<=limit or type(max_pages) is not int or not 1<=max_pages<=100:raise AdapterContractError('PULL_PAGING_INVALID')
        start=paging.get('start_page',1)
        if type(start) is not int or start<0:raise AdapterContractError('PULL_PAGING_INVALID')
        records=[];seen=set()
        for page in range(start,start+max_pages):
            context=self._request_context(adapter,{'data_type':data_type,'mode':mode,'cursor':cursor,'page':page,'offset':(page-start)*page_size,'limit':min(page_size,limit-len(records)),'idempotency_key':''})
            batch,next_cursor,has_more=self._page(config,request_spec,response_spec,context,credentials,timeout_seconds)
            records.extend(batch)
            if not has_more:return {'records':records,'next_cursor':next_cursor,'complete':True,'has_more':False,'truncated':False}
            if not batch or len(records)>=limit:raise AdapterContractError('PULL_WINDOW_EXCEEDS_LIMIT')
            if paging.get('mode','cursor')=='cursor':
                if not next_cursor or next_cursor==cursor or next_cursor in seen:raise AdapterContractError('PULL_CURSOR_NOT_ADVANCING')
                seen.add(next_cursor);cursor=next_cursor
            elif paging.get('mode')!='page':raise AdapterContractError('PULL_PAGING_INVALID')
        raise AdapterContractError('PULL_PAGE_LIMIT_EXCEEDED')

    def _page(self,config,request_spec,response_spec,context,credentials,timeout_seconds):
        response = self._request_json(endpoint=str(config.get('endpoint', '')).strip(), spec=request_spec,
                                      context=context, credentials=credentials, timeout_seconds=timeout_seconds)
        if not isinstance(response_spec, dict):
            raise AdapterContractError('PULL_RESPONSE_SPEC_INVALID')
        success_path = str(response_spec.get('success_path', '')).strip()
        if success_path:
            allowed = response_spec.get('success_values', [True, 0, '0', 'SUCCESS', 'OK'])
            if not matches_value(path_get(response, success_path),allowed):
                raise AdapterContractError('PULL_UPSTREAM_REJECTED')
        records = path_get(response, str(response_spec.get('records_path', 'data')))
        if not isinstance(records, list) or any(not isinstance(x, dict) for x in records):
            raise AdapterContractError('PULL_RECORDS_INVALID')
        if len(records) > context['limit']:
            raise AdapterContractError('PULL_PAGE_EXCEEDS_LIMIT')
        next_cursor = None
        cursor_path = str(response_spec.get('next_cursor_path', '')).strip()
        if cursor_path:
            raw_cursor = path_get(response, cursor_path, None)
            if raw_cursor not in (None, ''):
                next_cursor = str(raw_cursor)
                if len(next_cursor) > 500:
                    raise AdapterContractError('PULL_CURSOR_INVALID')
        has_more_path = str(response_spec.get('has_more_path', '')).strip()
        has_more = normalized_bool(path_get(response, has_more_path)) if has_more_path else False
        return records,next_cursor,has_more
