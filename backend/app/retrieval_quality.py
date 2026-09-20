"""Retrieval concepts and catalog grounding, never canned answers/business names."""
import json
import re
import sqlite3
from backend.app.temporal import plain

STOP = set('hola giana necesito quiero podés podes puedes decirme digas saber algún algun alguna lugar lugares donde dónde qué que me te se si hay para por favor un una unos unas de del la el los las en y o a al lo es son con tengo recomendaras recomiendes recomendame ciudad'.split())


def retrieval_terms(query):
    terms = [x for x in re.findall(r'\w+', plain(query)) if len(x) > 2 and x not in STOP]
    if re.search(r'\b(asados?|parrilladas?|carne a la parrilla)\b', plain(query)):
        terms += ['parrilla']
    if re.search(r'\b(perros?|gatos?|mascotas?)\b', plain(query)):
        terms += ['mascotas', 'perros']
    return list(dict.fromkeys(terms))[:32]


def search_query(query):
    return ' '.join(retrieval_terms(query)) or query


def catalog_candidates(db_path, query):
    """Match domain categories + zone, or a named entity, using the actual catalog."""
    q = plain(query)
    cook_own = bool(re.search(r'\b(hacer|preparar|cocinar|llevar|parrilleros?)\b', q))
    categories = []
    rules = [
        (r'\b(asados?|parrilladas?|parrillas?)\b', 'parrilla'),
        (r'\b(helado|helados|heladeria)\b', 'heladeria'),
        (r'\b(pizza|pizzas|pizzeria)\b', 'pizzeria'),
        (r'\b(cafe|cafeteria|merendar)\b', 'cafeteria'),
        (r'\b(hotel|hoteles)\b', 'hotel'),
        (r'\b(dormir|alojarme|alojamiento|hospedarme)\b', 'alojamiento'),
        (r'\b(acampar|camping)\b', 'camping'),
    ]
    for pattern, category in rules:
        if re.search(pattern, q) and not (category == 'parrilla' and cook_own):
            categories.append(category)
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT e.*, GROUP_CONCAT(c.category) categories FROM entities e LEFT JOIN entity_categories c USING(entity_id) GROUP BY e.entity_id').fetchall()
    zones = sorted({plain(r['zone']) for r in rows}, key=len, reverse=True)
    zone = next((z for z in zones if z in q), None)
    hits = []
    for row in rows:
        name = plain(row['name'])
        # Permit "Don Jorgito" for "Parrillada Don Jorgito", not generic shared words.
        distinctive = re.sub(r'^(parrillada|restaurante|hotel|posada|heladeria)\s+', '', name)
        named = name in q or (len(distinctive) > 5 and distinctive in q)
        category_match = bool(categories) and any(c in plain(row['categories'] or '').split(',') for c in categories)
        if not named and not (category_match and zone and plain(row['zone']) == zone):
            continue
        text = f"{row['name']}. Zona: {row['zone']}. Estado en catálogo: {row['status']}.\n{row['description']}"
        hits.append({'chunk_id': row['entity_id'], 'title': row['name'], 'text': text,
                     'start_line': row['start_line'], 'end_line': row['end_line'],
                     'source_refs': sorted({int(n) for n in re.findall(r'\[(\d+)\]', text)}),
                     'catalog_match': 'name' if named else 'category_zone', 'zone': row['zone']})
    return hits[:16]


def parent_evidence(db_path, rows):
    """Unify lexical blocks and dense chunks at their common parent, restoring context."""
    merged = {}
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        for item in rows:
            parent = item.get('block_id')
            if not parent:
                found = db.execute('SELECT block_id FROM chunks WHERE chunk_id=?', (item.get('chunk_id'),)).fetchone()
                parent = found['block_id'] if found else item.get('chunk_id')
            block = db.execute('SELECT * FROM source_blocks WHERE block_id=?', (parent,)).fetchone()
            candidate = dict(item)
            if block:
                candidate.update(chunk_id=parent, block_id=parent, title=block['title'],
                                 text=block['heading_path'] + '\n' + block['text'][:12000], start_line=block['start_line'], end_line=block['end_line'],
                                 source_refs=json.loads(block['source_refs'] or '[]'))
            key = candidate.get('chunk_id')
            if key in merged:
                merged[key]['rrf'] = merged[key].get('rrf', 0) + candidate.get('rrf', 0)
            else:
                merged[key] = candidate
    return list(merged.values())
