"""
日本国内 鉱物産地推定スクリプト v3 (config駆動型)
産総研 20万分の1日本シームレス地質図V2 を使用

使用方法:
  python analyze_minerals.py                    # 全鉱物を解析
  python analyze_minerals.py opal gold jade     # 指定鉱物のみ
"""

import sys
import geopandas as gpd
import pandas as pd
import numpy as np
import folium
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

from minerals_config import MINERALS, DEFAULT_MINERALS
from score_extras import build_holocene_volcanic_index

# ── パス設定 ──────────────────────────────────────────────────
BASE  = Path(__file__).parent
DATA  = BASE / "files" / "seamlessV2"
RIVER = BASE / "files" / "rivers"
OUT   = BASE / "output"
OUT.mkdir(exist_ok=True)
RIVER.mkdir(exist_ok=True)

# ── 対象鉱物の決定 ────────────────────────────────────────────
target_keys = sys.argv[1:] if len(sys.argv) > 1 else list(MINERALS.keys())
target_keys = [k for k in target_keys if k in MINERALS]
if not target_keys:
    print(f"有効な鉱物キーを指定してください: {list(MINERALS.keys())}")
    sys.exit(1)
print(f"解析対象: {[MINERALS[k]['name_ja'] for k in target_keys]}")

# ── 1. 地質データ読み込み ──────────────────────────────────────
print("\n地質データ読み込み中...")
poly   = gpd.read_file(DATA / "seamlessV2_poly.shp")
line   = gpd.read_file(DATA / "seamlessV2_line.shp")
legend = pd.read_csv(DATA / "legend.tsv", sep="\t", encoding="utf-8")

poly.columns   = [c.lower() for c in poly.columns]
legend.columns = [c.lower() for c in legend.columns]
poly_joined = poly.merge(legend, on="symbol", how="left")
print(f"  ポリゴン数: {len(poly_joined):,} / ライン数: {len(line):,}")

# ── 2. スコアリングエンジン ────────────────────────────────────

def calc_age_multiplier(age_ja, age_bonus_map):
    for keyword, mult in age_bonus_map.items():
        if keyword in str(age_ja):
            return mult
    return 1.0  # 年代不明はペナルティなし（中立）

def calc_mineral_score(row, mineral_cfg):
    lith_ja  = str(row.get("lithology_ja", ""))
    lith_en  = str(row.get("lithology_en", ""))
    group_ja = str(row.get("group_ja", ""))
    age_ja   = str(row.get("formationage_ja", ""))

    score = 0.0
    for tier in mineral_cfg["tiers"]:
        hit = (
            any(kw in lith_ja  for kw in tier["keywords_ja"]) or
            any(kw in lith_en  for kw in tier["keywords_en"]) or
            any(kw in group_ja for kw in tier.get("group_ja", []))
        )
        if hit:
            score = tier["score"]
            break

    if score == 0:
        return 0.0

    mult = calc_age_multiplier(age_ja, mineral_cfg.get("age_bonus", {}))
    return round(score * mult, 2)

# ── 3. 全鉱物スコア計算 ────────────────────────────────────────
print("スコア計算中...")
for key in target_keys:
    cfg = MINERALS[key]
    col = f"score_{key}"
    poly_joined[col] = poly_joined.apply(
        lambda r, c=cfg: calc_mineral_score(r, c), axis=1
    )

# いずれかの鉱物でスコアがあるポリゴンを抽出
score_cols = [f"score_{k}" for k in target_keys]
poly_joined["total_score"] = poly_joined[score_cols].sum(axis=1)
candidates = poly_joined[poly_joined["total_score"] > 0].copy()
print(f"  有望ポリゴン数: {len(candidates):,} / {len(poly_joined):,}")

# ── 4. 断層近接チェック（空間インデックス法）────────────────────
# unary_union は 45万ラインで極めて遅い。
# 代わりに候補ポリゴンの重心を 5km バッファ → sjoin で断層ラインと交差判定。
# sjoin は R木インデックスを使うため O(n log m) で大幅高速。
print("断層近接チェック中（空間インデックス + sjoin）...")
PROJ = "EPSG:6677"
cands_proj = candidates.to_crs(PROJ)
line_proj  = line.to_crs(PROJ)

# 候補ポリゴンの重心を 5km バッファした GeoDataFrame を作成
cands_proj["centroid"] = cands_proj.geometry.centroid
cands_buf = cands_proj.copy()
cands_buf.geometry = cands_proj["centroid"].buffer(5_000)

# sjoin で断層ラインと交差するものを抽出
joined = gpd.sjoin(
    cands_buf[["geometry"]],
    line_proj[["geometry"]],
    how="inner",
    op="intersects"
)
near_fault_idx = set(joined.index)
cands_proj["near_fault"] = cands_proj.index.isin(near_fault_idx)
print(f"  断層 5km 以内: {cands_proj['near_fault'].sum():,} ポリゴン")

for key in target_keys:
    bonus = MINERALS[key]["fault_bonus"]   # 乗算因子: score *= (1 + bonus)
    col   = f"score_{key}"
    mask  = cands_proj["near_fault"] & (cands_proj[col] > 0)
    cands_proj.loc[mask, col] = (cands_proj.loc[mask, col] * (1 + bonus)).round(2)

cands_proj["total_score"] = cands_proj[score_cols].sum(axis=1)

# ── 4b. 熱水変質スコア ─────────────────────────────────────────
print("熱水変質スコア計算中...")
holocene_gdf = build_holocene_volcanic_index(poly_joined)
if holocene_gdf is not None and len(holocene_gdf) > 0:
    print(f"  完新世火山岩ポリゴン: {len(holocene_gdf):,}")
    holocene_sindex = holocene_gdf.sindex

    def min_dist_to_holocene(centroid):
        bounds = centroid.buffer(15_000).bounds
        cand_idx = list(holocene_sindex.intersection(bounds))
        if not cand_idx:
            return float('inf')
        return holocene_gdf.geometry.iloc[cand_idx].distance(centroid).min()

    min_dists = cands_proj["centroid"].apply(min_dist_to_holocene)
    cands_proj["score_hydrothermal"] = min_dists.map(lambda d:
        3.0 if d == 0 else
        2.0 if d < 5_000 else
        1.0 if d < 10_000 else
        0.0
    )
    print(f"  熱水変質スコア > 0: {(cands_proj['score_hydrothermal'] > 0).sum():,} ポリゴン")
else:
    cands_proj["score_hydrothermal"] = 0.0
    print("  完新世火山岩データなし → 熱水変質スコア = 0")

# 熱水変質スコアを鉱物ごとの hydrothermal_weight で加算（共通一括加算を廃止）
for key in target_keys:
    w   = MINERALS[key].get("hydrothermal_weight", 0.5)
    col = f"score_{key}"
    if w > 0:
        mask = cands_proj[col] > 0
        cands_proj.loc[mask, col] = (
            cands_proj.loc[mask, col] + cands_proj.loc[mask, "score_hydrothermal"] * w
        ).round(2)

cands_proj["total_score"] = cands_proj[score_cols].sum(axis=1)
# score_hydrothermal は参照用として CSV に残す（各 score_* には既に反映済み）

# ── 5. 河川データ（存在する場合のみ）─────────────────────────
river_gdf = None
river_files = list(RIVER.glob("**/*.shp"))
if river_files:
    print(f"河川データ読み込み: {river_files[0].name}")
    river_gdf = gpd.read_file(river_files[0]).to_crs(PROJ)

    for key in target_keys:
        range_km = MINERALS[key]["river_range_km"]
        mask_geo = cands_proj[cands_proj[f"score_{key}"] > 0].geometry
        if len(mask_geo) == 0:
            river_gdf[f"river_{key}"] = False
            continue
        zone = mask_geo.buffer(0).unary_union
        river_gdf[f"river_{key}"] = river_gdf.geometry.intersects(zone)

    river_priority = river_gdf[
        [f"river_{k}" for k in target_keys if f"river_{k}" in river_gdf.columns]
    ].any(axis=1)
    river_gdf["any_priority"] = river_priority
    print(f"  優先河川セグメント: {river_priority.sum():,}")
else:
    print("河川データ未取得 → python download_rivers.py を先に実行してください")

# ── 6. 座標・東京距離計算 ─────────────────────────────────────
print("座標計算中...")
cands_wgs84 = cands_proj.to_crs("EPSG:4326")
cands_wgs84["lon"] = cands_wgs84.geometry.centroid.apply(lambda p: p.x)
cands_wgs84["lat"] = cands_wgs84.geometry.centroid.apply(lambda p: p.y)

def haversine(lon, lat, lon0=139.6917, lat0=35.6895):
    R = 6371
    dlat = np.radians(lat - lat0)
    dlon = np.radians(lon - lon0)
    a = (np.sin(dlat/2)**2 +
         np.cos(np.radians(lat0)) * np.cos(np.radians(lat)) * np.sin(dlon/2)**2)
    return 2 * R * np.arcsin(np.sqrt(a))

cands_wgs84["dist_tokyo_km"] = haversine(
    cands_wgs84["lon"].values, cands_wgs84["lat"].values
).round(1)

# ── 6b. 既知産地スコア（ベクトル化バッチ計算）───────────────────
print("既知産地スコア計算中...")
from score_extras import KNOWN_LOCALITIES

def _locality_score_batch(lats_arr, lons_arr, mineral_key,
                           thresholds=((20, 3.0), (50, 2.0))):
    """全ポリゴンに対して既知産地スコアをベクトル計算"""
    locs = KNOWN_LOCALITIES.get(mineral_key, [])
    n    = len(lats_arr)
    if not locs:
        return np.zeros(n), np.full(n, '', dtype=object)
    R      = 6371.0
    lats_r = np.radians(np.asarray(lats_arr, dtype=float))
    lons_r = np.radians(np.asarray(lons_arr, dtype=float))
    best_s = np.zeros(n)
    best_n = np.full(n, '', dtype=object)
    for name, loc_lat, loc_lon, conf, note in locs:
        lr    = np.radians(loc_lat); lor = np.radians(loc_lon)
        dlat  = lats_r - lr; dlon = lons_r - lor
        a     = np.sin(dlat/2)**2 + np.cos(lr) * np.cos(lats_r) * np.sin(dlon/2)**2
        dists = 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        for max_km, base in thresholds:
            mask = dists <= max_km
            if not mask.any():
                continue
            adj    = base * (conf / 3.0)
            better = mask & (adj > best_s)
            if better.any():
                best_s[better] = adj
                for i in np.where(better)[0]:
                    best_n[i] = f"{name}（{dists[i]:.0f}km）"
            break  # この産地は最初に合致した閾値のみ適用
    return np.round(best_s, 2), best_n.tolist()

lats_arr = cands_wgs84["lat"].values
lons_arr = cands_wgs84["lon"].values
for key in target_keys:
    s_arr, n_arr = _locality_score_batch(lats_arr, lons_arr, key)
    cands_wgs84[f"score_locality_{key}"] = s_arr
    cands_wgs84[f"nearest_{key}"]        = n_arr
    hits = (s_arr > 0).sum()
    print(f"  {MINERALS[key]['name_ja']}: 産地スコア > 0 = {hits:,} ポリゴン")

# ── 7. CSV 出力 ────────────────────────────────────────────────
base_cols = ["symbol", "near_fault", "dist_tokyo_km", "lon", "lat",
             "formationage_ja", "group_ja", "lithology_ja", "lithology_en",
             "total_score"]
locality_cols = (
    [f"score_locality_{k}" for k in target_keys] +
    [f"nearest_{k}"        for k in target_keys]
)
out_cols = base_cols + score_cols + ["score_hydrothermal"] + locality_cols
result_df = cands_wgs84[[c for c in out_cols if c in cands_wgs84.columns]].copy()
result_df = result_df.sort_values("total_score", ascending=False)
csv_path = OUT / "mineral_candidates.csv"
result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"CSV 保存: {csv_path}")

# ── 8. Folium インタラクティブ地図 ────────────────────────────
print("地図生成中...")

m = folium.Map(location=[36.5, 137.0], zoom_start=5, tiles="CartoDB positron")

folium.Marker(
    [35.6895, 139.6917],
    popup="<b>東京（起点）</b>",
    icon=folium.Icon(color="blue", icon="home", prefix="fa")
).add_to(m)

# 各鉱物レイヤー
for key in target_keys:
    cfg   = MINERALS[key]
    col   = f"score_{key}"
    layer = folium.FeatureGroup(name=cfg["name_ja"], show=(key in DEFAULT_MINERALS))
    top   = result_df[result_df[col] > 0].nlargest(200, col)
    s_max = top[col].max() if len(top) > 0 else 1.0

    for _, row in top.iterrows():
        ratio = row[col] / s_max
        # スコアに応じて透明度を変える（同じ色、濃淡で表現）
        opacity = 0.4 + 0.6 * ratio
        popup_html = (
            f"<b>{cfg['name_ja']}</b><br>"
            f"<b>スコア:</b> {row[col]:.1f}<br>"
            f"<b>岩相:</b> {row.get('lithology_ja','')}<br>"
            f"<b>年代:</b> {row.get('formationage_ja','')}<br>"
            f"<b>東京から:</b> {row['dist_tokyo_km']:.0f} km<br>"
            f"<b>断層近接:</b> {'○' if row['near_fault'] else '×'}<br>"
            f"<small>採取: {cfg['collection_tip']}</small>"
        )
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5 + ratio * 4,
            color=cfg["color"],
            fill=True, fill_color=cfg["color"],
            fill_opacity=opacity,
            popup=folium.Popup(popup_html, max_width=320)
        ).add_to(layer)
    layer.add_to(m)

# 複合有望地点レイヤー（2種類以上スコアがある地点）
multi_layer = folium.FeatureGroup(name="★ 複合有望地点", show=True)
has_multi = result_df[[c for c in score_cols]].gt(0).sum(axis=1) >= 2
multi_top = result_df[has_multi].nlargest(80, "total_score")

for _, row in multi_top.iterrows():
    hits = [MINERALS[k]["name_ja"] for k in target_keys if row.get(f"score_{k}", 0) > 0]
    popup_html = (
        f"<b>★ 複合有望地点</b><br>"
        f"<b>期待鉱物:</b> {'・'.join(hits)}<br>"
        f"<b>合計スコア:</b> {row['total_score']:.1f}<br>"
        f"<b>岩相:</b> {row.get('lithology_ja','')}<br>"
        f"<b>年代:</b> {row.get('formationage_ja','')}<br>"
        f"<b>東京から:</b> {row['dist_tokyo_km']:.0f} km"
    )
    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=folium.Popup(popup_html, max_width=320),
        icon=folium.Icon(color="red", icon="star", prefix="fa")
    ).add_to(multi_layer)
multi_layer.add_to(m)

# 河川レイヤー
if river_gdf is not None:
    river_wgs84 = river_gdf.to_crs("EPSG:4326")
    for key in target_keys:
        col = f"river_{key}"
        if col not in river_wgs84.columns:
            continue
        rl = folium.FeatureGroup(name=f"{MINERALS[key]['name_ja']}優先河川", show=False)
        for _, row in river_wgs84[river_wgs84[col]].iterrows():
            try:
                if row.geometry.geom_type == "LineString":
                    coords = [(y, x) for x, y in row.geometry.coords]
                else:
                    coords = [(y, x) for x, y in row.geometry.geoms[0].coords]
                folium.PolyLine(
                    coords, color=MINERALS[key]["color"],
                    weight=3, opacity=0.8,
                    popup=f"{MINERALS[key]['name_ja']}採取優先河川"
                ).add_to(rl)
            except Exception:
                continue
        rl.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

# 凡例
legend_items = "".join(
    f'<span style="color:{MINERALS[k]["color"]}">●</span> {MINERALS[k]["name_ja"]}<br>'
    for k in target_keys
)
legend_html = f"""
<div style="position:fixed;bottom:30px;left:30px;z-index:1000;
            background:white;padding:14px;border-radius:8px;
            border:1px solid #aaa;font-size:12px;line-height:1.9">
  <b>鉱物ポテンシャルマップ</b><br>
  {legend_items}
  <span style="color:red">★</span> 複合有望地点<br>
  <span style="color:blue">⌂</span> 東京（起点）<br>
  <small>● の大きさ＝スコア、濃さ＝確率</small>
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

map_path = OUT / "mineral_map.html"
m.save(str(map_path))
print(f"地図保存: {map_path}")

# ── 9. サマリー ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("【鉱物有望地域 サマリー】")
print("=" * 60)

for key in target_keys:
    cfg = MINERALS[key]
    col = f"score_{key}"
    top = result_df[result_df[col] > 0].nlargest(8, col)
    if len(top) == 0:
        continue
    print(f"\n▼ {cfg['name_ja']} (硬度:{cfg['hardness']} 比重:{cfg['sg']} "
          f"川での移動:{cfg['river_range_km']}km以内)")
    disp = top[["symbol", col, "dist_tokyo_km", "lithology_ja"]].copy()
    disp["dist_tokyo_km"] = disp["dist_tokyo_km"].round(0).astype(int)
    disp = disp.rename(columns={col: "スコア", "dist_tokyo_km": "東京(km)"})
    print(disp.to_string(index=False))

print(f"\n▼ 複合有望地点 Top10（複数鉱物が期待できる地点）")
if has_multi.any():
    multi_show = multi_top.head(10)[
        ["symbol", "total_score", "dist_tokyo_km", "lithology_ja"] + score_cols
    ].copy()
    multi_show["dist_tokyo_km"] = multi_show["dist_tokyo_km"].round(0).astype(int)
    print(multi_show.to_string(index=False))

print(f"\n出力:")
print(f"  {csv_path}")
print(f"  {map_path}")
