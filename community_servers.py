"""Community servers and member-only text channels."""
from datetime import datetime, timedelta, timezone
import re

TABLES = (
    'community_servers', 'community_channels',
    'community_server_members', 'community_channel_messages',
)
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS community_servers (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS community_channels (
        id TEXT PRIMARY KEY, server_id TEXT NOT NULL REFERENCES community_servers(id) ON DELETE CASCADE,
        name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0, UNIQUE(server_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS community_server_members (
        server_id TEXT NOT NULL REFERENCES community_servers(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        muted_until TEXT, joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(server_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS community_channel_messages (
        id TEXT PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES community_channels(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        body TEXT NOT NULL DEFAULT '', reply_id TEXT REFERENCES community_channel_messages(id) ON DELETE SET NULL,
        post_id TEXT REFERENCES community_posts(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0 CHECK(removed IN (0, 1))
    )""",
    'CREATE INDEX IF NOT EXISTS community_channels_messages_page ON community_channel_messages(channel_id,created_at DESC,id DESC)',
    'CREATE INDEX IF NOT EXISTS community_channels_messages_author ON community_channel_messages(user_id)',
    'CREATE INDEX IF NOT EXISTS community_servers_members_user ON community_server_members(user_id)',
)
MAX_HISTORY = 250
ID = r'[A-Za-z0-9_-]{1,100}'


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    return value.strftime('%Y-%m-%d %H:%M:%S.%f')


def membership(db, server, uid):
    return db.execute(
        'SELECT joined_at,muted_until FROM community_server_members WHERE server_id=? AND user_id=?',
        (server, uid),
    ).fetchone()


def can_moderate(db, uid, core):
    return bool(uid and core['is_admin'](db, uid))


def public_post_rule(viewer):
    import community as c

    rule, args = c.acl(viewer)
    return "p.status='published' AND p.audience='public' AND cp.visibility='public' AND " + rule, args


def post_for_share(db, post, viewer):
    if not isinstance(post, str) or not re.fullmatch(ID, post):
        return None
    rule, args = public_post_rule(viewer)
    return db.execute(
        "SELECT p.id,p.title FROM community_posts p JOIN community_profiles cp ON cp.user_id=p.user_id "
        "WHERE p.id=? AND " + rule,
        (post, *args),
    ).fetchone()


def add_channel(db, server, name, position, core):
    channel = core['ident']()
    result = db.execute(
        'INSERT INTO community_channels(id,server_id,name,position) VALUES(?,?,?,?) '
        'ON CONFLICT(server_id,name) DO NOTHING RETURNING id',
        (channel, server, name, position),
    ).fetchone()
    if not result:
        raise core['HttpError'](409, 'That channel already exists.')
    return channel


def read_messages(db, channel, uid, limit):
    post_rule, post_args = public_post_rule(uid)
    rows = db.execute(f"""WITH recent AS (
        SELECT m.id,m.user_id,m.body,m.reply_id,m.post_id,m.created_at,u.display_name
        FROM community_channel_messages m JOIN users u ON u.id=m.user_id
        WHERE m.channel_id=? AND m.removed=0 AND u.suspended=0
        AND NOT EXISTS (SELECT 1 FROM community_blocks b WHERE
            (b.user_id=? AND b.target_id=m.user_id) OR (b.target_id=? AND b.user_id=m.user_id))
        ORDER BY m.created_at DESC,m.id DESC LIMIT ?
    )
    SELECT recent.id,recent.user_id,recent.body,recent.created_at,recent.display_name,
        COALESCE(av.value,'') AS avatar_url,p.id AS shared_id,p.title AS shared_title,
        ru.display_name AS reply_name,CASE WHEN ru.id IS NOT NULL THEN r.body END AS reply_body
    FROM recent
    LEFT JOIN platform_config av ON av.key='public_avatar:'||recent.user_id
    LEFT JOIN community_channel_messages r ON r.id=recent.reply_id AND r.channel_id=? AND r.removed=0
    LEFT JOIN users ru ON ru.id=r.user_id AND ru.suspended=0
        AND NOT EXISTS (SELECT 1 FROM community_blocks b WHERE
            (b.user_id=? AND b.target_id=ru.id) OR (b.target_id=? AND b.user_id=ru.id))
    LEFT JOIN community_posts p ON p.id=recent.post_id AND EXISTS (
        SELECT 1 FROM community_profiles cp WHERE cp.user_id=p.user_id AND {post_rule})
    ORDER BY recent.created_at DESC,recent.id DESC
    """, (channel, uid, uid, limit + 1, channel, uid, uid, *post_args)).fetchall()

    messages = []
    for row in reversed(rows[:limit]):
        message = dict(row)
        shared_id, shared_title = message.pop('shared_id'), message.pop('shared_title')
        reply_name, reply_body = message.pop('reply_name'), message.pop('reply_body')
        message['post'] = {'id': shared_id, 'title': shared_title} if shared_id else None
        message['reply'] = {'name': reply_name, 'body': reply_body[:160]} if reply_body is not None else None
        messages.append(message)
    return {'messages': messages, 'has_older': len(rows) > limit}


def route(db, ctx, method, part, qs, data, core):
    import community as c

    uid = ctx['uid']
    if part == '/servers' and method == 'GET':
        servers = db.execute(
            """SELECT s.id,s.name,s.description,CASE WHEN m.joined_at IS NULL THEN 0 ELSE 1 END AS joined
               FROM community_servers s LEFT JOIN community_server_members m ON m.server_id=s.id AND m.user_id=?
               ORDER BY s.created_at,s.id""", (uid or '',),
        ).fetchall()
        return {'servers': [dict(s) for s in servers], 'can_manage': can_moderate(db, uid, core)}

    if part == '/servers' and method == 'POST':
        admin = core['require_admin'](ctx)
        name = c.text(core, data.get('name'), 48, 2)
        description = c.text(core, data.get('description', ''), 180)
        server = core['ident']()
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('INSERT INTO community_servers(id,name,description) VALUES(?,?,?)', (server, name, description))
            for position, label in enumerate(('general', 'find-a-team', 'clips')):
                add_channel(db, server, label, position, core)
            core['audit'](db, admin, 'community.server_created', 'community_server', server)
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            raise
        return 201, {'id': server}

    path = re.fullmatch(rf'/servers/({ID})(/.*)?', part)
    if not path:
        c.fail(core, 404, 'Server unavailable.')
    server, action = path.groups()
    info = db.execute('SELECT id,name,description FROM community_servers WHERE id=?', (server,)).fetchone()
    if not info:
        c.fail(core, 404, 'Server unavailable.')

    member = membership(db, server, uid)
    joined = bool(member and member['joined_at'])
    moderator = can_moderate(db, uid, core)
    if not action and method == 'GET':
        channels = db.execute(
            'SELECT id,name FROM community_channels WHERE server_id=? ORDER BY position,name,id', (server,),
        ).fetchall()
        return {
            **dict(info), 'channels': [dict(row) for row in channels],
            'joined': joined, 'can_manage': moderator,
        }

    if action == '/join' and method == 'POST':
        c.ensure_profile(db, ctx, core)
        db.execute(
            'INSERT INTO community_server_members(server_id,user_id,joined_at) VALUES(?,?,?) '
            'ON CONFLICT(server_id,user_id) DO UPDATE SET joined_at=COALESCE(community_server_members.joined_at,excluded.joined_at)',
            (server, uid, stamp(now())),
        )
        return {'joined': True}

    if action == '/leave' and method == 'POST':
        # Preserve active mutes when a member leaves and rejoins.
        db.execute('UPDATE community_server_members SET joined_at=NULL WHERE server_id=? AND user_id=?', (server, uid))
        return {'joined': False}

    if action == '/channels' and method == 'POST':
        admin = core['require_admin'](ctx)
        name = c.text(core, data.get('name'), 32, 2).lower()
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
            c.fail(core, 400, 'Use letters a–z, numbers and hyphens for the channel name.')
        created = add_channel(db, server, name, 100, core)
        core['audit'](db, admin, 'community.channel_created', 'community_channel', created)
        return 201, {'id': created}

    messages = re.fullmatch(rf'/channels/({ID})/messages(?:/({ID})(/mute)?)?', action or '')
    if not messages:
        c.fail(core, 404, 'Channel unavailable.')
    channel, message, moderation = messages.groups()
    if not uid:
        core['require_user'](ctx)
    if not joined:
        if not moderator:
            c.fail(core, 403, 'Join this server to read or send messages.')
        core['require_admin'](ctx)
    if not db.execute('SELECT 1 FROM community_channels WHERE id=? AND server_id=?', (channel, server)).fetchone():
        c.fail(core, 404, 'Channel unavailable.')

    if method == 'GET' and not message:
        try:
            limit = min(MAX_HISTORY, max(50, int(qs.get('limit', ['50'])[0])))
        except ValueError:
            c.fail(core, 400, 'Invalid page.')
        return read_messages(db, channel, uid, limit)

    if method == 'POST' and not message:
        if not joined:
            c.fail(core, 403, 'Join this server to read or send messages.')
        when = stamp(now())
        if member['muted_until'] and member['muted_until'] > when:
            c.fail(core, 403, 'You are temporarily muted in this server.')
        body = c.text(core, data.get('body', ''), 1000)
        post_id = data.get('post_id') or None
        if post_id and not post_for_share(db, post_id, uid):
            c.fail(core, 404, 'Only public Discover posts can be shared.')
        if not body and not post_id:
            c.fail(core, 400, 'Write a message or share a post.')
        reply_id = data.get('reply_id') or None
        if reply_id:
            if not isinstance(reply_id, str) or not re.fullmatch(ID, reply_id):
                c.fail(core, 404, 'Message unavailable.')
            reply = db.execute(
                'SELECT m.user_id FROM community_channel_messages m JOIN users u ON u.id=m.user_id '
                'WHERE m.channel_id=? AND m.id=? AND m.removed=0 AND u.suspended=0',
                (channel, reply_id),
            ).fetchone()
            if not reply or c.blocked(db, uid, reply['user_id']):
                c.fail(core, 404, 'Message unavailable.')
        core['check_rate'](db, 'community-channel-write', uid, 15, 30)
        message_id = core['ident']()
        # Check membership again at insertion so a concurrent mute or leave is respected.
        inserted = db.execute(
            """INSERT INTO community_channel_messages(id,channel_id,user_id,body,reply_id,post_id,created_at)
               SELECT ?,?,?,?,?,?,? FROM community_server_members WHERE server_id=? AND user_id=?
               AND joined_at IS NOT NULL AND (muted_until IS NULL OR muted_until<=?)
               RETURNING id""",
            (message_id, channel, uid, body, reply_id, post_id, when, server, uid, when),
        ).fetchone()
        if not inserted:
            c.fail(core, 403, 'You cannot send messages in this server right now.')
        return 201, {'id': message_id}

    if message:
        target = db.execute(
            'SELECT user_id FROM community_channel_messages WHERE channel_id=? AND id=?', (channel, message),
        ).fetchone()
        if not target:
            c.fail(core, 404, 'Message unavailable.')
        if method == 'DELETE' and not moderation:
            if target['user_id'] != uid:
                core['require_admin'](ctx)
            changed = db.execute(
                """UPDATE community_channel_messages SET removed=1,body='',post_id=NULL,reply_id=NULL
                   WHERE id=? AND removed=0""", (message,),
            ).rowcount
            if changed and target['user_id'] != uid:
                core['audit'](db, uid, 'community.channel_message_removed', 'community_channel_message', message)
            return {'ok': True}
        if method == 'POST' and moderation == '/mute':
            core['require_admin'](ctx)
            if can_moderate(db, target['user_id'], core):
                c.fail(core, 400, 'Administrators cannot be muted here.')
            mute = data.get('enabled')
            if type(mute) is not bool:
                c.fail(core, 400, 'Choose enabled or disabled.')
            until = stamp(now() + timedelta(hours=1)) if mute else None
            db.execute(
                '''INSERT INTO community_server_members(server_id,user_id,joined_at,muted_until) VALUES(?,?,NULL,?)
                   ON CONFLICT(server_id,user_id) DO UPDATE SET muted_until=excluded.muted_until''',
                (server, target['user_id'], until),
            )
            core['audit'](db, uid, 'community.server_mute', 'community_server', server,
                          {'target': target['user_id'], 'enabled': mute})
            return {'ok': True}
    c.fail(core, 404, 'Channel unavailable.')
