"""Public information pages shared by the server and localized browser UI."""
import html
import json
from pathlib import Path

CONTENT = json.loads((Path(__file__).parent / 'static' / 'info-pages-content.json').read_text(encoding='utf-8'))
PAGES_BY_PATH = {page['path']: (route, page) for route, page in CONTENT['pages'].items()}


def render(path):
    route, page = PAGES_BY_PATH[path]
    title = page['title']['en']
    lead = page['lead']['en']
    payload = {
        'route': route,
        'page': page,
        'salesNotice': CONTENT['salesNotice'],
    }
    if page.get('publisherList'):
        payload['publisherRules'] = CONTENT['publisherRules']
    payload_json = json.dumps(payload, ensure_ascii=False).replace('<', r'\u003c')
    parts = [
        '<section class="page info-page" data-info-route="'+html.escape(route, quote=True)+'">',
        '<header class="page-header"><div><h1 class="page-title">'+html.escape(title)+'</h1>',
        '<p class="page-subtitle">'+html.escape(lead)+'</p></div></header><article class="legal-copy">',
    ]
    if page.get('showSalesNotice'):
        parts.append('<p class="notice warn">'+html.escape(CONTENT['salesNotice']['en'])+'</p>')
    for index, section in enumerate(page['sections'], start=1):
        section_id = section.get('id', f'info-section-{index}')
        parts.append(f'<section class="info-section" id="{html.escape(section_id, quote=True)}"><h2>{html.escape(section["title"]["en"])}</h2>')
        # Paragraphs and bullets are trusted editorial content containing links.
        parts.extend(f'<p>{paragraph["en"]}</p>' for paragraph in section['paragraphs'])
        if section['bullets']:
            parts.append('<ul>'+''.join(f'<li>{bullet["en"]}</li>' for bullet in section['bullets'])+'</ul>')
        parts.append('</section>')
    if page.get('publisherList'):
        parts.append('<section class="info-section"><h2>Official publisher rules</h2><ul>')
        for name, url, description in CONTENT['publisherRules']:
            parts.append(f'<li><a href="{html.escape(url, quote=True)}">{html.escape(name)}</a> · {html.escape(description["en"])}</li>')
        parts.append('</ul></section>')
    if page.get('action'):
        parts.append('<p><a href="/contact">Contact support</a></p>')
    parts.append('</article></section><script type="application/json" id="public-info-content">'+payload_json+'</script>')
    return page.get('metadataTitle', page['title'])['en']+' — SentryLoot', lead, ''.join(parts)
