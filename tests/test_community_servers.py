"""HTTP coverage for Community server permissions and message visibility."""
import unittest

import app
from tests import test_community as community_fixtures
from tests import test_http_workflows as http_fixtures


class CommunityServersTest(unittest.TestCase):
    setUp = http_fixtures.HTTPWorkflows.setUp
    tearDown = http_fixtures.HTTPWorkflows.tearDown
    signed_client = http_fixtures.HTTPWorkflows.signed_client
    req = community_fixtures.CommunityWorkflows.req

    def create_server(self, name):
        status, result, _ = self.req(self.admin, 'POST', '/servers', {'name': name})
        self.assertEqual(status, 201, result)
        route = '/servers/' + result['id']
        room = self.req(self.guest, 'GET', route)[1]
        self.assertEqual([channel['name'] for channel in room['channels']], ['general', 'find-a-team', 'clips'])
        return route, room

    def test_server_management_and_membership_permissions(self):
        self.assertEqual(self.req(self.guest, 'GET', '/servers')[1]['servers'], [])
        self.assertEqual(self.req(self.seller, 'POST', '/servers', {'name': 'Unauthorized'})[0], 403)
        route, room = self.create_server('PUBG Mobile')
        general = route + '/channels/' + room['channels'][0]['id'] + '/messages'
        self.assertEqual(self.req(self.guest, 'GET', general)[0], 401)
        self.assertEqual(self.req(self.seller, 'GET', general)[0], 403)
        self.assertEqual(self.req(self.seller, 'POST', route + '/join', {}, csrf=False)[0], 403)
        self.assertEqual(self.req(self.seller, 'POST', route + '/join', {})[1], {'joined': True})
        self.assertEqual(self.req(self.seller, 'POST', route + '/join', {})[1], {'joined': True})
        self.assertEqual(self.req(self.seller, 'GET', '/servers')[1]['servers'][0]['joined'], 1)
        self.assertEqual(self.req(self.seller, 'GET', general)[1]['messages'], [])
        self.assertEqual(self.req(self.seller, 'POST', route + '/channels', {'name': 'ranked'})[0], 403)
        self.assertEqual(self.req(self.admin, 'POST', route + '/channels', {'name': 'ranked'})[0], 201)
        self.assertEqual(self.req(self.admin, 'POST', route + '/channels', {'name': 'RANKED'})[0], 409)
        self.assertEqual(self.req(self.seller, 'POST', route + '/leave', {})[0], 200)
        self.assertEqual(self.req(self.seller, 'GET', general)[0], 403)
        self.assertEqual(self.req(self.seller, 'POST', general, {'body': 'Hello'})[0], 403)

    def test_messages_replies_shares_and_moderation(self):
        route, room = self.create_server('Valorant')
        self.req(self.seller, 'POST', route + '/join', {})
        general, clips = [route + '/channels/' + room['channels'][i]['id'] + '/messages' for i in (0, 2)]
        status, original, _ = self.req(self.seller, 'POST', general, {'body': 'Anyone want to play?'})
        self.assertEqual(status, 201)
        self.assertEqual(self.req(self.seller, 'POST', clips, {'body': 'I do', 'reply_id': original['id']})[0], 404)
        self.assertEqual(self.req(self.seller, 'POST', general, {'body': 'Ready', 'reply_id': original['id']})[0], 201)
        data = {
            'title': 'A public Discover clip', 'body': 'Ready to play', 'kind': 'moment',
            'game_slug': 'valorant', 'audience': 'public', 'permission': True,
        }
        status, draft, _ = self.req(self.seller, 'POST', '/posts', {**data, 'status': 'draft'})
        self.assertEqual(status, 201)
        status, post, _ = self.req(self.seller, 'POST', '/discover/posts', {**data, 'status': 'published'})
        self.assertEqual(status, 201, post)
        self.assertEqual(self.req(self.seller, 'POST', clips, {'post_id': draft['id']})[0], 404)
        self.assertEqual(self.req(self.seller, 'POST', clips, {'post_id': post['id']})[0], 201)
        self.assertEqual(self.req(self.admin, 'GET', clips)[1]['messages'][0]['post']['id'], post['id'])
        self.assertEqual(self.req(self.admin, 'GET', general)[1]['messages'][1]['reply']['body'], 'Anyone want to play?')
        self.assertEqual(self.req(self.seller, 'DELETE', '/posts/' + post['id'])[0], 200)
        self.assertIsNone(self.req(self.seller, 'GET', clips)[1]['messages'][0]['post'])

        mute = general + '/' + original['id'] + '/mute'
        self.assertEqual(self.req(self.seller, 'POST', mute, {'enabled': True})[0], 403)
        self.assertEqual(self.req(self.admin, 'POST', mute, {'enabled': True})[0], 200)
        self.req(self.seller, 'POST', route + '/leave', {})
        self.req(self.seller, 'POST', route + '/join', {})
        self.assertEqual(self.req(self.seller, 'POST', clips, {'body': 'Still muted'})[0], 403)
        self.assertEqual(self.req(self.admin, 'POST', mute, {'enabled': False})[0], 200)
        self.assertEqual(self.req(self.admin, 'DELETE', general + '/' + original['id'])[0], 200)
        messages = self.req(self.seller, 'GET', general)[1]['messages']
        self.assertEqual([row['body'] for row in messages], ['Ready'])
        self.assertIsNone(messages[0]['reply'])
        self.assertEqual(self.req(self.seller, 'POST', clips, {'body': 'Back again'})[0], 201)

    def test_blocked_and_suspended_authors_do_not_appear_in_channel(self):
        route, room = self.create_server('Counter-Strike 2')
        channel = route + '/channels/' + room['channels'][0]['id'] + '/messages'
        self.req(self.seller, 'POST', route + '/join', {})
        self.req(self.admin, 'POST', route + '/join', {})
        self.assertEqual(self.req(self.admin, 'POST', channel, {'body': 'Admin message'})[0], 201)
        self.assertEqual(len(self.req(self.seller, 'GET', channel)[1]['messages']), 1)
        self.assertEqual(self.req(self.seller, 'POST', '/profiles/' + self.admin_id + '/block', {'enabled': True})[0], 200)
        self.assertEqual(self.req(self.seller, 'GET', channel)[1]['messages'], [])
        self.req(self.seller, 'POST', '/profiles/' + self.admin_id + '/block', {'enabled': False})
        self.db.execute('UPDATE users SET suspended=1 WHERE id=?', (self.admin_id,))
        self.assertEqual(self.req(self.seller, 'GET', channel)[1]['messages'], [])
