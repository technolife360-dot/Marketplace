"""Versioned seller choices. Competitor taxonomy is not publisher authorization.

No network calls or bulk database writes occur on requests/cold starts. Only the
game actually used by a seller is persisted by app.resolve_game_id.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

CATEGORIES = frozenset(('accounts', 'items', 'currency', 'codes', 'top-ups', 'services', 'digital'))


def normalize(value):
    return re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', str(value)).casefold()).strip()


@lru_cache(maxsize=1)
def catalogue():
    return json.loads((Path(__file__).parent / 'data' / 'seller-catalog.json').read_text())


@lru_cache(maxsize=1)
def index():
    result = {}
    for game in catalogue()['games']:
        for value in [game['id'], game['name'], *game.get('aliases', [])]:
            result.setdefault(normalize(value), game)
    return result


def find(value):
    return index().get(normalize(value))


@lru_cache(maxsize=1)
def artwork():
    path=Path(__file__).parent / 'data' / 'seller-catalog-images.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def image_url(game_id):
    value=artwork().get(game_id,{}).get('url','')
    return value if re.fullmatch(r'https://images\.gamestorehub\.com/admin-images/catalogue-icons/v1/[a-z0-9-]+-[0-9a-f]{20}\.webp',value) else ''


def public_games():
    return [{'id': game['id'], 'slug': game['id'], 'name': game['name'],
             'aliases': game.get('aliases', []),
             'supported_categories': sorted(game['categories']),
             'image_url': image_url(game['id'])}
            for game in catalogue()['games']]


def validate_selection(db, value, category_id, error):
    game = find(value)
    if not game:
        row = db.execute('SELECT slug,name FROM games WHERE id=?', (value,)).fetchone()
        if row:
            game = find(row['slug']) or find(row['name'])
    # Unknown products keep the existing private moderation/request path.
    if not game:
        return
    category = db.execute('SELECT slug FROM categories WHERE id=?', (category_id,)).fetchone()
    if category and category['slug'] not in game['categories']:
        raise error(400, 'This game or brand is not available for the selected product type. Choose a matching game or product type.')
