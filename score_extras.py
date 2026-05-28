# -*- coding: utf-8 -*-
"""
追加評価スコアモジュール

1. hydrothermal_score  : 熱水変質プロキシ（完新世火山岩への近接 + OSM温泉）
2. known_locality_score: 既知産地との照合（国内鉱物産地データベース）
3. river_access_score  : 河川アクセス（OSM Overpass API による水系密度）
"""

import numpy as np
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# ① 既知産地データベース
# 出典: 産総研 MRDB、鉱物同好会記録、文献調査（2025年時点）
# ═══════════════════════════════════════════════════════════════

KNOWN_LOCALITIES = {

    "opal": [
        # 名称, 緯度, 経度, 信頼度(1-3), 備考
        ("島根県 出雲市多伎町",         35.37, 132.55, 3, "出雲オパール。中新世珪質頁岩"),
        ("島根県 奥出雲町（仁多）",      35.18, 133.02, 3, "仁多の虹。熱水変質帯"),
        ("島根県 雲南市",               35.32, 132.90, 2, "出雲周辺広域"),
        ("北海道 沙流郡平取町",          42.58, 142.10, 2, "日高山脈周辺"),
        ("北海道 留萌郡",               44.00, 141.90, 2, "石狩炭田周辺"),
        ("岩手県 雫石町",               39.70, 140.93, 2, "奥羽山脈火山帯"),
        ("宮城県 大崎市鳴子",           38.73, 140.61, 3, "鳴子温泉。熱水変質激しい"),
        ("新潟県 佐渡市",               38.03, 138.37, 2, "金山周辺の珪質岩"),
        ("新潟県 阿賀町",               37.73, 139.45, 2, "緑色凝灰岩帯"),
        ("静岡県 伊豆市",               34.89, 138.94, 2, "伊豆火山弧"),
        ("大分県 由布市湯布院",          33.27, 131.37, 3, "ハイアライト産地。活火山近傍"),
        ("大分県 豊後大野市",            32.97, 131.61, 2, "阿蘇外輪山火砕流"),
        ("宮崎県 宮崎市",               31.91, 131.42, 2, "鮮新〜更新世火砕流"),
        ("鹿児島県 霧島市",             31.74, 130.73, 2, "霧島火山"),
        ("熊本県 阿蘇市",               32.88, 131.10, 2, "阿蘇カルデラ"),
        ("長崎県 壱岐市",               33.79, 129.70, 2, "玄武岩〜流紋岩互層"),
        ("北海道 釧路市",               42.97, 144.38, 2, "白亜紀珪質岩"),
    ],

    "gold": [
        ("新潟県 佐渡市（相川金山）",    38.03, 138.24, 3, "世界的金銀山。浅熱水型"),
        ("鹿児島県 伊佐市菱刈",          32.03, 130.60, 3, "菱刈金山。現役最大鉱山"),
        ("秋田県 小坂町",               40.34, 140.58, 3, "黒鉱（kuroko）型"),
        ("秋田県 羽後町（院内）",        39.44, 140.45, 2, "院内銀山"),
        ("北海道 札幌市南区豊羽",        42.89, 141.13, 3, "豊羽鉱山。Pb-Zn-Au"),
        ("北海道 留萌管内砂金川",        43.90, 141.80, 2, "砂金の名所"),
        ("北海道 日高山脈",              42.70, 142.60, 2, "金-銅鉱床帯"),
        ("岩手県 久慈市（田野畑周辺）",  40.18, 141.84, 2, "砂金採取地"),
        ("富山県 黒部川上流",            36.82, 137.61, 2, "砂金川"),
        ("静岡県 伊豆市（土肥）",        34.89, 138.76, 3, "土肥金山。浅熱水型"),
        ("鹿児島県 南九州市（知覧）",    31.36, 130.44, 2, "南九州火山弧"),
        ("宮崎県 串間市",               31.47, 131.23, 2, "南九州金鉱帯"),
        ("島根県 大田市（石見銀山）",    35.09, 132.43, 3, "石見銀山。金も伴出"),
        ("兵庫県 朝来市（生野）",        35.01, 134.83, 3, "生野銀山"),
        ("長野県 木曽郡大桑村",          35.63, 137.67, 2, "砂金採取地"),
        ("岐阜県 益田川（下呂）",        35.80, 137.24, 2, "砂金"),
    ],

    "jade": [
        ("新潟県 糸魚川市（小滝川）",    37.04, 137.86, 3, "世界最大翡翠産地。姫川水系"),
        ("新潟県 糸魚川市（青海川）",    37.03, 137.75, 3, "翡翠海岸"),
        ("富山県 朝日町（境川）",        36.97, 137.64, 2, "姫川系"),
        ("長野県 白馬村",               36.72, 137.86, 2, "蛇紋岩帯"),
        ("京都府 南丹市美山",            35.30, 135.60, 2, "丹波帯蛇紋岩"),
        ("高知県 四万十川上流",          33.50, 133.00, 2, "三波川変成帯"),
        ("熊本県 球磨川上流",            32.45, 130.92, 2, "蛇紋岩"),
    ],

    "quartz": [
        ("山梨県 甲州市（乙女鉱山）",    35.78, 138.82, 3, "甲州水晶。ペグマタイト"),
        ("山梨県 山梨市（牧丘）",        35.73, 138.78, 3, "水晶の里"),
        ("岐阜県 中津川市",             35.49, 137.50, 2, "花崗岩ペグマタイト"),
        ("福島県 石川郡（好間）",        37.08, 140.49, 2, "花崗岩ペグマタイト"),
        ("茨城県 常陸太田市",            36.54, 140.52, 2, "水晶・長石"),
        ("北海道 日高地方",              42.50, 142.00, 2, "変成岩帯"),
        ("長崎県 対馬市",               34.41, 129.33, 2, "花崗岩ペグマタイト"),
        ("岡山県 真庭市（美星）",        34.89, 133.54, 2, "花崗岩帯"),
    ],

    "garnet": [
        ("奈良県 吉野郡天川村",          34.27, 135.87, 3, "ザクロ石片岩"),
        ("埼玉県 秩父郡長瀞",            36.12, 139.11, 3, "結晶片岩。博物館あり"),
        ("岡山県 新見市（満奇洞周辺）",  34.95, 133.50, 2, "スカルン帯"),
        ("愛媛県 西条市（黒瀬川）",      33.85, 133.08, 2, "スカルン・変成岩"),
        ("北海道 日高山脈",              42.50, 142.50, 2, "変成岩帯"),
        ("長野県 木曽郡上松町",          35.77, 137.68, 2, "結晶片岩"),
        ("静岡県 天竜川上流",            35.10, 137.85, 2, "領家変成帯"),
    ],

    "magnetite": [
        ("岩手県 釜石市（釜石鉱山）",    39.27, 141.88, 3, "日本最大のスカルン鉱床"),
        ("岡山県 津山市（柵原）",        34.95, 134.20, 2, "スカルン型"),
        ("北海道 函館市（恵山）",        41.80, 141.18, 2, "砂鉄浜"),
        ("静岡県 富士川河口",            35.15, 138.60, 3, "砂鉄。富士火山由来"),
        ("鹿児島県 桜島周辺",            31.58, 130.65, 3, "砂鉄。現役火山"),
        ("秋田県 男鹿半島",             39.90, 139.90, 2, "砂鉄浜"),
        ("島根県 出雲市（砂鉄川）",      35.47, 132.96, 3, "たたら製鉄。砂鉄産地"),
    ],

    "fluorite": [
        ("福島県 田村市（神俣鉱山）",    37.47, 140.58, 3, "紫蛍石。熱水脈型"),
        ("石川県 小松市尾小屋",          36.35, 136.59, 3, "尾小屋鉱山"),
        ("岐阜県 神岡町",               36.32, 137.27, 3, "神岡鉱山。蛍石を伴出"),
        ("北海道 紋別郡（鴻之舞）",      44.18, 143.41, 2, "熱水型金-蛍石"),
        ("長野県 川上村",               35.88, 138.58, 2, "花崗岩帯熱水脈"),
    ],

    "stibnite": [
        ("愛媛県 西条市市ノ川",          33.78, 133.14, 3, "世界的名産地。長柱状結晶"),
        ("高知県 宿毛市（大月）",        32.80, 132.80, 2, "輝安鉱"),
        ("鹿児島県 指宿市",             31.25, 130.63, 2, "熱水型"),
        ("北海道 夕張市",               43.05, 141.97, 2, "熱水脈"),
    ],

    "rhodochrosite": [
        ("静岡県 伊豆市（土肥鉱山）",    34.90, 138.76, 3, "菱マンガン鉱の銘産地"),
        ("岩手県 大船渡市（大谷鉱山）",  39.11, 141.75, 3, "大谷鉱山"),
        ("北海道 三笠市（幌内）",        43.35, 141.78, 2, "Mn鉱床"),
        ("広島県 三次市",               34.80, 133.00, 2, "Mn熱水鉱床"),
    ],
}


def known_locality_score(lat, lon, mineral_key,
                          thresholds=((20, 3.0), (50, 2.0), (100, 1.0))):
    """
    既知産地との距離に基づくスコア加算
    thresholds: [(距離km, スコア), ...] 近い順に評価
    """
    localities = KNOWN_LOCALITIES.get(mineral_key, [])
    if not localities:
        return 0.0, None

    best_score = 0.0
    nearest = None
    for name, loc_lat, loc_lon, confidence, note in localities:
        dist = haversine_km(lat, lon, loc_lat, loc_lon)
        for max_km, base_score in thresholds:
            if dist <= max_km:
                adj = base_score * (confidence / 3.0)  # 信頼度で補正
                if adj > best_score:
                    best_score = adj
                    nearest = (name, dist, note)
                break
    return round(best_score, 2), nearest


# ═══════════════════════════════════════════════════════════════
# ② 熱水変質プロキシスコア
# ═══════════════════════════════════════════════════════════════

def build_holocene_volcanic_index(poly_gdf, proj_crs="EPSG:6677"):
    """
    完新世・後期更新世の火山岩ポリゴンをまとめて
    空間インデックス用の GeoDataFrame を返す
    """
    age_col  = "formationage_ja" if "formationage_ja" in poly_gdf.columns else "formationage_ja"
    lith_col = "lithology_ja"    if "lithology_ja"    in poly_gdf.columns else "lithology_ja"

    is_recent_volcanic = (
        poly_gdf[age_col].str.contains("完新世|更新世 後期|Holocene|Late Pleistocene",
                                        na=False, regex=True) &
        poly_gdf[lith_col].str.contains("火山岩|デイサイト|流紋岩|安山岩|玄武岩",
                                         na=False, regex=True)
    )
    recent = poly_gdf[is_recent_volcanic].copy()
    if len(recent) == 0:
        return None
    return recent.to_crs(proj_crs)


def hydrothermal_score_from_geo(centroid_proj, holocene_gdf,
                                 hot_spring_union=None,
                                 proj_crs="EPSG:6677"):
    """
    熱水変質プロキシスコア
      +3: 完新世火山岩の上 or 直接重なる（活発な火山域）
      +2: 5km 以内に完新世火山岩
      +1: 10km 以内 / もしくは OSM 温泉が 5km 以内
    """
    if holocene_gdf is None or len(holocene_gdf) == 0:
        return 0.0

    # 空間インデックスで最近傍距離を取得
    distances = holocene_gdf.geometry.distance(centroid_proj)
    min_dist  = distances.min()

    if min_dist == 0:
        return 3.0
    elif min_dist < 5_000:
        score = 2.0
    elif min_dist < 10_000:
        score = 1.0
    else:
        score = 0.0

    # OSM 温泉の近接ボーナス
    if hot_spring_union is not None:
        hs_dist = centroid_proj.distance(hot_spring_union)
        if hs_dist < 5_000:
            score = min(score + 1.0, 3.0)

    return score


# ═══════════════════════════════════════════════════════════════
# ③ 河川アクセス（OSM Overpass API）
# ═══════════════════════════════════════════════════════════════

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

def river_access_score(lat, lon, radius_m=5000, timeout=10):
    """
    OSM Overpass API で半径 radius_m 以内の水系を取得しスコアを返す
      +3: 名前付き河川（river）あり
      +2: 小河川（stream）あり
      +1: 水路・溝（canal/drain）のみ
      0 : 水系なし
    また河川名のリストも返す
    """
    query = f"""
[out:json][timeout:{timeout}];
(
  way["waterway"="river"](around:{radius_m},{lat},{lon});
  way["waterway"="stream"](around:{radius_m},{lat},{lon});
  way["waterway"="canal"](around:{radius_m},{lat},{lon});
);
out tags;
"""
    try:
        data = urllib.parse.urlencode({"data": query}).encode()
        req  = urllib.request.Request(
            OVERPASS_URL, data=data,
            headers={"User-Agent": "OpalInJp/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            result = json.loads(resp.read().decode())
    except Exception as e:
        return 0.0, [], str(e)

    elements = result.get("elements", [])
    rivers  = []
    streams = []
    canals  = []

    for el in elements:
        tags = el.get("tags", {})
        wtype = tags.get("waterway", "")
        name  = tags.get("name:ja") or tags.get("name", "")
        if wtype == "river":
            if name and name not in rivers:
                rivers.append(name)
        elif wtype == "stream":
            if name and name not in streams:
                streams.append(name)
        elif wtype in ("canal", "drain"):
            canals.append(name)

    if rivers:
        return 3.0, rivers, None
    elif streams:
        return 2.0, streams[:3], None
    elif canals:
        return 1.0, [], None
    else:
        return 0.0, [], None


# ═══════════════════════════════════════════════════════════════
# ユーティリティ
# ═══════════════════════════════════════════════════════════════

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (np.sin(dlat/2)**2 +
         np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2)
    return 2 * R * np.arcsin(np.sqrt(a))
