"""Bounded data-hub pages with durable worker-owned continuation checkpoints."""
from hashlib import sha256
from .contracts import AdapterContractError
from .common import parse_credential


def pull_chunk(adapter, *, data_type, mode, cursor, limit, checkpoint=None,
               config, credential, timeout_seconds):
    if mode not in {'FULL', 'INCREMENTAL'} or type(limit) is not int or not 1 <= limit <= 1000:
        raise AdapterContractError('PULL_REQUEST_INVALID')
    settings = adapter._adapter_config(config)
    spec = (settings.get('data_types') or {}).get(data_type)
    if not isinstance(spec, dict):
        raise AdapterContractError('PULL_DATA_TYPE_NOT_CONFIGURED')
    paging, response = spec.get('pagination') or {}, spec.get('response') or {}
    size, maximum = paging.get('page_size', limit), paging.get('max_pages', 100)
    start = paging.get('start_page', 1)
    if (type(size) is not int or not 1 <= size <= limit or type(maximum) is not int
            or not 1 <= maximum <= 100 or type(start) is not int or start < 0):
        raise AdapterContractError('PULL_PAGING_INVALID')
    kind = paging.get('mode', 'cursor')
    if kind not in {'cursor', 'page'}:
        raise AdapterContractError('PULL_PAGING_INVALID')
    state = checkpoint or {'page': start, 'cursor': cursor, 'seen': []}
    if not isinstance(state, dict) or set(state) != {'page', 'cursor', 'seen'}:
        raise AdapterContractError('PULL_PAGING_INVALID')
    page, position, seen = state['page'], state['cursor'], state['seen']
    if (type(page) is not int or page < start or not isinstance(seen, list)
            or len(seen) > 100 or any(not isinstance(x, str) or len(x) != 64 for x in seen)
            or position is not None and (not isinstance(position, str) or len(position) > 500)):
        raise AdapterContractError('PULL_PAGING_INVALID')
    if page - start >= maximum:
        raise AdapterContractError('PULL_PAGE_LIMIT_EXCEEDED')
    has_marker = bool(response.get('has_more_path'))
    if not has_marker and paging.get('end_condition') != 'short_page':
        raise AdapterContractError('PULL_COMPLETENESS_RULE_REQUIRED')
    context = adapter._request_context(settings, {'data_type': data_type, 'mode': mode,
        'cursor': position, 'page': page, 'offset': (page-start)*size,
        'limit': size, 'idempotency_key': ''})
    batch, next_cursor, more, metadata = adapter._page(
        config, spec.get('request'), response, context, parse_credential(credential),
        timeout_seconds, with_metadata=True)
    if not has_marker:
        more = len(batch) == size
    following = None
    if more:
        if not batch:
            raise AdapterContractError('PULL_CURSOR_NOT_ADVANCING')
        if kind == 'cursor':
            if not next_cursor or next_cursor == position:
                raise AdapterContractError('PULL_CURSOR_NOT_ADVANCING')
            stamp = sha256(next_cursor.encode()).hexdigest()
            if stamp in seen:
                raise AdapterContractError('PULL_CURSOR_NOT_ADVANCING')
            seen = [*seen, stamp]
        following = {'page': page+1, 'cursor': next_cursor if kind == 'cursor' else cursor, 'seen': seen}
    return {'records': batch, 'has_more': more, 'checkpoint': following,
            'page': page, 'source_total': metadata['total'],
            'next_cursor': metadata['watermark'] if metadata['watermark'] is not None else next_cursor}
