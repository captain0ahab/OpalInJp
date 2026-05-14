# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template
from pathlib import Path
import pandas as pd
import numpy as np
import json, os

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

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

    keep = ['lat', 'lon', 'dist_km', 'sort_score', 'total_score',
            'lithology_ja', 'formationage_ja', 'near_fault', 'dist_tokyo_km']
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
