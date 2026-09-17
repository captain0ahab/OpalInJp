# -*- coding: utf-8 -*-
"""/api/search の numpy 実装の最小自己チェック。  実行: python test_app.py"""
import json, os
os.environ.pop('SUPABASE_URL', None)
import app

c = app.app.test_client()

r = c.get('/api/search?lat=36.5&lon=136.6&radius_km=20&mineral=all').get_json()
assert r['count'] > 0 and 0 < len(r['results']) <= 80
assert isinstance(r['results'][0]['near_fault'], bool)
scores = [x['sort_score'] for x in r['results']]
assert scores == sorted(scores, reverse=True), 'スコア降順になっていない'
assert r['max_score'] == scores[0]
json.dumps(r)  # numpy 型が混ざっていれば TypeError

g = c.get('/api/search?lat=35.2&lon=138.9&radius_km=50&mineral=gold').get_json()
assert g['sort_col'] == 'score_gold'
assert all(x['score_gold'] > 0 for x in g['results'])

e = c.get('/api/search?lat=30.0&lon=131.0&radius_km=5&mineral=all').get_json()
assert e['count'] == 0 and e['results'] == []

assert c.get('/api/search?lat=abc&lon=1').status_code == 400
print('OK')
