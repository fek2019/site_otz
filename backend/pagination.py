from flask import request


def parse_limit_offset(default_limit=20, max_limit=100):
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', type=int)

    if limit is None:
        limit = default_limit
    if offset is None:
        offset = 0

    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)

    return limit, offset


def build_pagination_payload(total, limit, offset):
    return {
        'total': int(total or 0),
        'limit': limit,
        'offset': offset,
        'has_more': offset + limit < int(total or 0),
    }
