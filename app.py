# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template
from pathlib import Path
import pandas as pd
import numpy as np
import json, os
import urllib.request, urllib.parse

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

from score_extras import KNOWN_LOCALITIES, haversine_km as _loc_hav

_LOC_THRESHOLDS = ((20, 3.0), (50, 2.0))

def _locality_score(lat, lon, mineral):
    """既知産地との距離スコアをリアルタイム計算（上位 80 件分のみ）"""
    if mineral == 'all':
        loc_items = list(KNOWN_LOCALITIES.items())
    else:
        loc_items = [(mineral, KNOWN_LOCALITIES.get(mineral, []))]

    best_score = 0.0
    best_note  = ''
    for m_key, locs in loc_items:
        m_name = MINERAL_LABELS.get(m_key, m_key)
        for name, loc_lat, loc_lon, conf, note in locs:
            dist = _loc_hav(lat, lon, loc_lat, loc_lon)
            for max_km, base in _LOC_THRESHOLDS:
                if dist <= max_km:
                    adj = base * (conf / 3.0)
                    if adj > best_score:
                        best_score = adj
                        best_note  = f"{name}（{dist:.0f}km、{m_name}）"
                    break
    return round(best_score, 2), best_note

# 比重（g/cm³）→ 川での移動距離の逆数として上流参照半径を決定
MINERAL_DENSITY = {
    'gold': 19.3, 'magnetite': 5.2, 'stibnite': 4.6,
    'garnet': 3.9, 'rhodochrosite': 3.7, 'jade': 3.3,
    'fluorite': 3.2, 'quartz': 2.65, 'opal': 2.1,
}

def _density_radius(mineral):
    """比重から上流参照半径(km)を算出: radius = 10 * (2.65 / density)"""
    d = MINERAL_DENSITY.get(mineral, 5.0)
    return round(10.0 * (2.65 / d), 1)


BASE = Path(__file__).parent
df = pd.read_csv(BASE / 'output' / 'mineral_candidates.csv', encoding='utf-8-sig')
print(f"データ読み込み完了: {len(df):,} ポリゴン")

MINERAL_LABELS = {
    'opal':         'オパール',
    'gold':         '砂金',
    'jade':         '翡翠',
    'quartz':       '水晶',
    'garnet':       'ザクロ石',
    'magnetite':    '磁鉄鉱',
    'fluorite':     '蛍石',
    'stibnite':     '輝安鉱',
    'rhodochrosite':'菱マンガン鉱',
}

MINERAL_COLORS = {
    'all':          '#2980b9',
    'opal':         '#e74c3c',
    'gold':         '#f39c12',
    'jade':         '#27ae60',
    'quartz':       '#9b59b6',
    'garnet':       '#c0392b',
    'magnetite':    '#95a5a6',
    'fluorite':     '#1abc9c',
    'stibnite':     '#2c3e50',
    'rhodochrosite':'#e91e63',
}

mineral_score_cols = [c for c in df.columns
                      if c.startswith('score_') and c != 'score_hydrothermal']

# 起動時に文字列 NaN を処理しておく
for col in ['lithology_ja', 'formationage_ja', 'group_ja']:
    if col in df.columns:
        df[col] = df[col].fillna('—')
df['near_fault'] = df['near_fault'].astype(bool)


def haversine_vec(lat, lon, lats, lons):
    R = 6371.0
    dlat = np.radians(lats - lat)
    dlon = np.radians(lons - lon)
    a = (np.sin(dlat / 2) ** 2 +
         np.cos(np.radians(lat)) * np.cos(np.radians(lats)) * np.sin(dlon / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


@app.route('/')
def index():
    return render_template('index.html',
                           minerals=MINERAL_LABELS,
                           colors=MINERAL_COLORS)


@app.route('/api/search')
def search():
    try:
        lat       = float(request.args['lat'])
        lon       = float(request.args['lon'])
        radius_km = float(request.args.get('radius_km', 20))
        mineral   = request.args.get('mineral', 'all')
    except (KeyError, ValueError) as e:
        return jsonify({'error': str(e)}), 400

    dists = haversine_vec(lat, lon, df['lat'].values, df['lon'].values)
    mask  = dists <= radius_km
    near  = df[mask].copy()
    near['dist_km'] = np.round(dists[mask], 1)

    color = MINERAL_COLORS.get(mineral, '#2980b9')

    if len(near) == 0:
        return jsonify({'count': 0, 'results': [], 'color': color, 'max_score': 1})

    if mineral == 'all':
        sort_col = 'total_score'
    else:
        sort_col = f'score_{mineral}'
        if sort_col in near.columns:
            near = near[near[sort_col] > 0]
        else:
            sort_col = 'total_score'

    if len(near) == 0:
        return jsonify({'count': 0, 'results': [], 'color': color, 'max_score': 1})

    top = near.nlargest(80, sort_col).copy()
    top['sort_score'] = top[sort_col].fillna(0).round(2)

    # 既知産地スコアをリアルタイム計算（80 件なので十分高速）
    loc_scores, loc_notes = [], []
    for _, row in top.iterrows():
        s, n = _locality_score(row['lat'], row['lon'], mineral)
        loc_scores.append(s)
        loc_notes.append(n)
    top['score_locality']    = loc_scores
    top['nearest_locality'] = loc_notes

    keep = ['lat', 'lon', 'dist_km', 'sort_score', 'total_score',
            'lithology_ja', 'formationage_ja', 'near_fault', 'dist_tokyo_km',
            'score_locality', 'nearest_locality']
    keep += [c for c in mineral_score_cols if c in top.columns]
    if 'score_hydrothermal' in top.columns:
        keep.append('score_hydrothermal')
    keep = [c for c in keep if c in top.columns]

    # pandas の to_json は NaN → null を自動処理
    records = json.loads(top[keep].to_json(orient='records', force_ascii=False))

    return jsonify({
        'count':          len(near),
        'results':        records,
        'sort_col':       sort_col,
        'color':          color,
        'max_score':      float(top['sort_score'].max()),
        'mineral_labels': MINERAL_LABELS,
    })


@app.route('/api/localities')
def localities():
    from score_extras import KNOWN_LOCALITIES
    items = []
    for mineral, locs in KNOWN_LOCALITIES.items():
        for name, lat, lon, confidence, note in locs:
            items.append({
                'mineral':      mineral,
                'mineral_name': MINERAL_LABELS.get(mineral, mineral),
                'name':         name,
                'lat':          lat,
                'lon':          lon,
                'confidence':   confidence,
                'note':         note,
            })
    return jsonify({'localities': items})


@app.route('/api/rivers')
def rivers_api():
    try:
        lat       = float(request.args['lat'])
        lon       = float(request.args['lon'])
        radius_km = float(request.args.get('radius_km', 20))
        mineral   = request.args.get('mineral', 'all')
    except (KeyError, ValueError) as e:
        return jsonify({'error': str(e)}), 400

    # バウンディングボックス
    deg   = radius_km / 111.0
    cos_l = np.cos(np.radians(lat))
    south, north = lat - deg, lat + deg
    west,  east  = lon - deg / cos_l, lon + deg / cos_l
    bbox  = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"

    query = (
        f'[out:json][timeout:25];'
        f'(way["waterway"~"^(river|stream)$"]({bbox}););'
        f'out geom;'
    )
    try:
        data = urllib.parse.urlencode({'data': query}).encode()
        req  = urllib.request.Request(
            'https://overpass-api.de/api/interpreter', data=data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent':   'OpalInJp/1.0 (mineral prospecting map)',
                'Accept':       'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            osm = json.loads(r.read().decode())
    except Exception as e:
        # Overpass 失敗時は空結果を返す（500 にしない）
        return jsonify({
            'type': 'FeatureCollection', 'features': [],
            'ref_radius': _density_radius(mineral), 'max_score': 1.0,
            'mineral': mineral, 'warning': str(e)
        })

    # 比重由来の上流参照半径
    ref_radius = _density_radius(mineral)

    # 検索範囲のポリゴンを絞り込む（numpy 配列で持つことで pandas インデックス問題を回避）
    dists = haversine_vec(lat, lon, df['lat'].values, df['lon'].values)
    mask  = dists <= radius_km
    near_lats   = df['lat'].values[mask]
    near_lons   = df['lon'].values[mask]

    sort_col = 'total_score' if mineral == 'all' else f'score_{mineral}'
    if sort_col not in df.columns:
        sort_col = 'total_score'
    near_scores = df[sort_col].values[mask]

    max_score = float(near_scores.max()) if len(near_scores) > 0 else 1.0

    # 各河川ウェイをスコアリング
    features = []
    for way in osm.get('elements', []):
        if way.get('type') != 'way' or 'geometry' not in way:
            continue
        geom = way['geometry']
        if len(geom) < 2:
            continue

        # サンプル点を最大8点に間引き
        step    = max(1, len(geom) // 8)
        samples = geom[::step]
        best    = 0.0
        for pt in samples:
            if len(near_lats) == 0:
                break
            d    = haversine_vec(pt['lat'], pt['lon'], near_lats, near_lons)
            pmask = d <= ref_radius
            if pmask.any():
                v = float(near_scores[pmask].max())
                if v > best:
                    best = v

        features.append({
            'type': 'Feature',
            'geometry': {
                'type':        'LineString',
                'coordinates': [[g['lon'], g['lat']] for g in geom],
            },
            'properties': {
                'score':    round(best, 2),
                'name':     way.get('tags', {}).get('name', ''),
                'waterway': way.get('tags', {}).get('waterway', 'stream'),
            }
        })

    return jsonify({
        'type':       'FeatureCollection',
        'features':   features,
        'ref_radius': ref_radius,
        'max_score':  max_score,
        'mineral':    mineral,
    })


@app.route('/api/overlays')
def overlays_api():
    try:
        lat       = float(request.args['lat'])
        lon       = float(request.args['lon'])
        radius_km = float(request.args.get('radius_km', 20))
    except (KeyError, ValueError) as e:
        return jsonify({'error': str(e)}), 400

    deg   = radius_km / 111.0
    cos_l = np.cos(np.radians(lat))
    south, north = lat - deg, lat + deg
    west,  east  = lon - deg / cos_l, lon + deg / cos_l
    bbox = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"

    query = (
        f'[out:json][timeout:30];'
        f'('
        f'relation["boundary"="national_park"]({bbox});'
        f'relation["boundary"="protected_area"]({bbox});'
        f'node["natural"="hot_spring"]({bbox});'
        f'node["natural"="fumarole"]({bbox});'
        f'node["historic"="mine"]({bbox});'
        f'way["historic"="mine"]({bbox});'
        f'node["man_made"="mineshaft"]({bbox});'
        f');'
        f'out center tags;'
    )
    try:
        data_enc = urllib.parse.urlencode({'data': query}).encode()
        req = urllib.request.Request(
            'https://overpass-api.de/api/interpreter', data=data_enc,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent':   'OpalInJp/1.0 (mineral prospecting map)',
                'Accept':       'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=35) as r:
            osm = json.loads(r.read().decode())
    except Exception as e:
        return jsonify({'parks': [], 'hotsprings': [], 'mines': [], 'warning': str(e)})

    parks, hotsprings, mines = [], [], []
    for el in osm.get('elements', []):
        tags  = el.get('tags', {})
        etype = el.get('type', '')
        name  = tags.get('name:ja') or tags.get('name') or ''

        if etype == 'node':
            lat_el, lon_el = el.get('lat'), el.get('lon')
        elif 'center' in el:
            lat_el, lon_el = el['center']['lat'], el['center']['lon']
        else:
            continue

        boundary = tags.get('boundary', '')
        if boundary in ('national_park', 'protected_area'):
            pc = int(tags.get('protect_class', 0) or 0)
            if boundary == 'national_park' or pc in (2, 3, 4, 5):
                if boundary == 'national_park' or pc == 2:
                    park_type = '国立公園'
                elif pc == 3:
                    park_type = '国定公園'
                else:
                    park_type = '自然公園'
                parks.append({'name': name, 'lat': lat_el, 'lon': lon_el, 'park_type': park_type})
            continue

        natural = tags.get('natural', '')
        if natural in ('hot_spring', 'fumarole'):
            hotsprings.append({'name': name or ('温泉' if natural == 'hot_spring' else '噴気孔'), 'lat': lat_el, 'lon': lon_el})
            continue

        if tags.get('historic') == 'mine' or tags.get('man_made') == 'mineshaft':
            mine_type = '旧鉱山' if tags.get('historic') == 'mine' else '坑道'
            mines.append({'name': name or mine_type, 'lat': lat_el, 'lon': lon_el, 'mine_type': mine_type})

    return jsonify({'parks': parks, 'hotsprings': hotsprings, 'mines': mines})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
