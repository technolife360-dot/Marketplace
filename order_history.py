"""Bounded order history summaries. Private delivery data is fetched only in detail views."""
import base64
import hashlib
import json
import re


def page(db, uid, qs, core):
    error = core['HttpError']
    value = lambda key, default='': qs.get(key, [default])[0]
    role, group, query = value('role', 'all'), value('status', 'all'), value('q').strip()
    if role not in ('all', 'purchases', 'sales') or group not in ('all', 'active', 'completed', 'closed') or len(query) > 100:
        raise error(400, 'Check order filters and search text.')
    try:
        limit = int(value('limit', '20'))
        if not 1 <= limit <= 50:
            raise ValueError()
    except (ValueError, TypeError):
        raise error(400, 'Choose between 1 and 50 orders per page.')
    where, args = [], []
    seller = 'o.id IN (SELECT member.order_id FROM order_items member WHERE member.seller_id=?)'
    if role == 'purchases':
        where.append('o.buyer_id=?'); args.append(uid)
    elif role == 'sales':
        where.append('o.buyer_id<>? AND '+seller); args.extend((uid, uid))
    else:
        where.append('(o.buyer_id=? OR '+seller+')'); args.extend((uid, uid))
    if group == 'active':
        where.append("o.status NOT IN ('completed','cancelled','refunded')")
    elif group == 'completed':
        where.append("o.status='completed'")
    elif group == 'closed':
        where.append("o.status IN ('cancelled','refunded')")
    if query:
        pattern = '%'+query.lower().replace('!', '!!').replace('%', '!%').replace('_', '!_')+'%'
        where.append("(LOWER(o.reference) LIKE ? ESCAPE '!' OR EXISTS(SELECT 1 FROM order_items search_item WHERE search_item.order_id=o.id AND (o.buyer_id=? OR search_item.seller_id=?) AND LOWER(search_item.title) LIKE ? ESCAPE '!'))")
        args.extend((pattern, uid, uid, pattern))
    scope = hashlib.sha256(json.dumps([uid, role, group, query], separators=(',', ':')).encode()).hexdigest()[:20]
    cursor = value('cursor')
    if cursor:
        try:
            if len(cursor) > 512:
                raise ValueError()
            stamp, oid, bound = json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
            if not isinstance(stamp, str) or not re.fullmatch(r'[0-9T:.+ Z-]{10,40}', stamp) or not isinstance(oid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', oid) or bound != scope:
                raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            raise error(400, 'This order page has expired. Start from the first page.')
        where.append('(o.created_at<? OR (o.created_at=? AND o.id<?))'); args.extend((stamp, stamp, oid))
    rows = [dict(row) for row in db.execute('SELECT o.id,o.reference,o.buyer_id,o.currency,o.total_minor,o.status,o.created_at FROM orders o WHERE '+' AND '.join(where)+' ORDER BY o.created_at DESC,o.id DESC LIMIT ?', (*args, limit+1))]
    more = len(rows) > limit
    rows = rows[:limit]
    by_id = {row['id']: row for row in rows}
    for row in rows:
        row['items'] = []
    if rows:
        marks = ','.join('?' for _ in rows)
        previews = db.execute(f'''WITH visible AS (
            SELECT i.id,i.order_id,ROW_NUMBER() OVER(PARTITION BY i.order_id ORDER BY i.id) row_position,
                COUNT(*) OVER(PARTITION BY i.order_id) item_count,
                SUM(i.unit_price_minor*i.quantity) OVER(PARTITION BY i.order_id) item_total
            FROM order_items i JOIN orders o ON o.id=i.order_id
            WHERE i.order_id IN ({marks}) AND (o.buyer_id=? OR i.seller_id=?)
        ) SELECT i.id,i.order_id,i.title,i.quantity,i.unit_price_minor,i.snapshot_json,v.item_count,v.item_total
            FROM visible v JOIN order_items i ON i.id=v.id WHERE v.row_position<=2 ORDER BY i.order_id,i.id''', (*by_id, uid, uid))
        for item in previews:
            row = by_id[item['order_id']]
            row['item_count'] = int(item['item_count'])
            if row['buyer_id'] != uid:
                row['total_minor'] = int(item['item_total'])
            try:
                snapshot = json.loads(item['snapshot_json'] or '{}')
            except (ValueError, TypeError):
                snapshot = {}
            if not isinstance(snapshot, dict):
                snapshot = {}
            safe = {key: snapshot[key] for key in ('image_url', 'game_name', 'product_type', 'platform', 'region') if key in snapshot}
            row['items'].append({'id': item['id'], 'title': item['title'], 'quantity': item['quantity'], 'unit_price_minor': item['unit_price_minor'], **safe, 'snapshot': safe})
    for row in rows:
        row['item_count'] = row.get('item_count', 0)
        if row['buyer_id'] != uid:
            row['buyer_id'] = None
    next_cursor = None
    if more:
        tail = rows[-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([str(tail['created_at']), tail['id'], scope], separators=(',', ':')).encode()).decode().rstrip('=')
    return {'items': rows, 'has_more': more, 'next_cursor': next_cursor, 'limit': limit}
