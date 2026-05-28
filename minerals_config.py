"""
日本で河川採取可能な鉱物の地質特性定義

各鉱物は以下の要素で定義される：
  lithology_ja      : 地質図の lithology_ja 列に含まれるキーワード → スコア
  lithology_en      : 地質図の lithology_en 列に含まれるキーワード → スコア
  group_ja          : 地質図の group_ja 列に含まれるキーワード → スコア
  age_bonus         : 地質年代キーワード → 乗数（デフォルト 1.0 = ペナルティなし）
  fault_bonus       : 断層近接時の乗数加算分 → score *= (1 + fault_bonus)
  hydrothermal_weight : 熱水変質スコア（0-3）への感度（0.0-1.0）
  river_range_km    : 母岩から河川を何km下流まで採取可能か（硬度・比重依存）
  hardness          : モース硬度
  sg                : 比重
  color             : 地図表示色
  collection_tip    : 採取のヒント
"""

MINERALS = {

    # ────────────────────────────────────────────────
    # オパール  SiO2·nH2O
    # 熱水性珪質鉱物。流紋岩・デイサイト中の空洞に沈殿。
    # ────────────────────────────────────────────────
    "opal": {
        "name_ja": "オパール",
        "name_en": "Opal",
        "hardness": 5.5,
        "sg": 2.0,
        "river_range_km": 8,
        "fault_bonus": 0.3,          # 断層近接で ×1.3
        "hydrothermal_weight": 1.0,  # 熱水珪化が主因
        "color": "#e74c3c",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["デイサイト", "流紋岩"],
             "keywords_en": ["dacite", "rhyolite"],
             "group_ja": [],
             "score": 3.0},
            {"keywords_ja": ["珪質"],
             "keywords_en": ["siliceous"],
             "group_ja": [],
             "score": 2.0},
            {"keywords_ja": ["チャート"],
             "keywords_en": ["chert", "metachert"],
             "group_ja": [],
             "score": 1.0},
        ],
        "age_bonus": {
            "中新世": 1.5, "Miocene": 1.5,
            "鮮新世": 1.3, "Pliocene": 1.3,
            "更新世": 1.2, "Pleistocene": 1.2,
            "完新世": 1.1, "Holocene": 1.1,
        },
        "collection_tip": "有望地質域の直下流・小支流の礫層を探す（10km以内）",
    },

    # ────────────────────────────────────────────────
    # 砂金  Au
    # 浅熱水型金鉱床（佐渡・菱刈等）、花崗岩石英脈型。
    # ────────────────────────────────────────────────
    "gold": {
        "name_ja": "砂金",
        "name_en": "Gold",
        "hardness": 2.5,
        "sg": 19.3,
        "river_range_km": 200,
        "fault_bonus": 0.4,          # 熱水鉱脈は断層制御が強い → ×1.4
        "hydrothermal_weight": 1.0,  # 浅熱水型金鉱床は熱水と直結
        "color": "#f39c12",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["デイサイト", "流紋岩"],
             "keywords_en": ["dacite", "rhyolite"],
             "group_ja": [],
             "score": 3.0},
            {"keywords_ja": ["花崗岩", "閃緑岩", "花崗閃緑岩"],
             "keywords_en": ["granite", "diorite", "granodiorite", "tonalite"],
             "group_ja": [],
             "score": 2.0},
            {"keywords_ja": ["安山岩", "玄武岩"],
             "keywords_en": ["andesite", "basalt"],
             "group_ja": [],
             "score": 2.0},
            {"keywords_ja": [],
             "keywords_en": ["metamorphic"],
             "group_ja": ["変成岩"],
             "score": 1.5},
            {"keywords_ja": [],
             "keywords_en": ["accretionary"],
             "group_ja": ["付加体"],
             "score": 1.0},
        ],
        "age_bonus": {
            "中新世": 1.5, "Miocene": 1.5,
            "鮮新世": 1.3, "Pliocene": 1.3,
            "白亜紀": 1.1, "Cretaceous": 1.1,
        },
        "collection_tip": "蛇行部の内側・岩盤露出箇所の砂礫底、パンニングで採取",
    },

    # ────────────────────────────────────────────────
    # 翡翠（ヒスイ輝石）  NaAlSi2O6
    # 高圧低温変成（青色片岩相）。蛇紋岩帯に伴う。
    # 熱水とは逆方向（低温高圧）のプロセスで生成。
    # ────────────────────────────────────────────────
    "jade": {
        "name_ja": "翡翠（ヒスイ）",
        "name_en": "Jadeite",
        "hardness": 6.5,
        "sg": 3.3,
        "river_range_km": 50,
        "fault_bonus": 0.1,          # 断層は構造的な位置づけのみ → ×1.1
        "hydrothermal_weight": 0.0,  # 高圧低温変成 → 熱水と無関係
        "color": "#27ae60",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["蛇紋岩"],
             "keywords_en": ["serpentinite", "serpentine"],
             "group_ja": [],
             "score": 3.0},
            {"keywords_ja": ["青色片岩", "藍閃石"],
             "keywords_en": ["blueschist", "glaucophane", "lawsonite"],
             "group_ja": [],
             "score": 3.0},
            {"keywords_ja": [],
             "keywords_en": [],
             "group_ja": ["変成岩"],
             "score": 0.5},
        ],
        "age_bonus": {
            "白亜紀": 1.5, "Cretaceous": 1.5,
            "ジュラ紀": 1.3, "Jurassic": 1.3,
            "三畳紀": 1.2, "Triassic": 1.2,
        },
        "collection_tip": "蛇紋岩帯の河川・海岸礫浜。白〜緑色の硬い石を探す",
    },

    # ────────────────────────────────────────────────
    # 水晶  SiO2
    # 花崗岩ペグマタイト・熱水石英脈に産出。全国分布。
    # ────────────────────────────────────────────────
    "quartz": {
        "name_ja": "水晶",
        "name_en": "Quartz Crystal",
        "hardness": 7.0,
        "sg": 2.65,
        "river_range_km": 50,
        "fault_bonus": 0.3,          # 断層沿いの石英脈 → ×1.3
        "hydrothermal_weight": 0.3,  # 熱水石英脈は存在するが主産地はペグマタイト
        "color": "#8e44ad",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["花崗岩", "ペグマタイト"],
             "keywords_en": ["granite", "pegmatite"],
             "group_ja": [],
             "score": 3.0},
            {"keywords_ja": ["デイサイト", "流紋岩"],
             "keywords_en": ["dacite", "rhyolite"],
             "group_ja": [],
             "score": 2.0},
            {"keywords_ja": ["閃緑岩", "花崗閃緑岩"],
             "keywords_en": ["diorite", "granodiorite", "tonalite"],
             "group_ja": [],
             "score": 1.5},
            {"keywords_ja": [],
             "keywords_en": ["metamorphic", "schist", "gneiss"],
             "group_ja": ["変成岩"],
             "score": 1.0},
        ],
        "age_bonus": {
            "白亜紀": 1.3, "Cretaceous": 1.3,
            "ジュラ紀": 1.2, "Jurassic": 1.2,
            "古第三紀": 1.1, "Paleogene": 1.1,
        },
        "collection_tip": "花崗岩帯の川底・崖の裂け目。六角柱状の透明な石英を探す",
    },

    # ────────────────────────────────────────────────
    # ザクロ石（鉄礬柘榴石）  Fe3Al2(SiO4)3
    # スカルン（接触変成岩）と変成岩の両方に産出。
    # ────────────────────────────────────────────────
    "garnet": {
        "name_ja": "ザクロ石（ガーネット）",
        "name_en": "Garnet",
        "hardness": 7.0,
        "sg": 3.9,
        "river_range_km": 30,
        "fault_bonus": 0.1,          # 変成岩産主体なので断層効果は小 → ×1.1
        "hydrothermal_weight": 0.2,  # スカルン帯は多少熱水を伴う
        "color": "#922b21",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["スカルン", "ホルンフェルス"],
             "keywords_en": ["skarn", "hornfels", "calc-silicate"],
             "group_ja": [],
             "score": 3.0},
            {"keywords_ja": ["結晶片岩", "片麻岩"],
             "keywords_en": ["schist", "gneiss", "crystalline"],
             "group_ja": ["変成岩"],
             "score": 2.0},
            {"keywords_ja": ["花崗岩", "閃緑岩"],
             "keywords_en": ["granite", "diorite", "granodiorite"],
             "group_ja": [],
             "score": 1.0},
        ],
        "age_bonus": {
            "白亜紀": 1.4, "Cretaceous": 1.4,
            "ジュラ紀": 1.2, "Jurassic": 1.2,
            "古生代": 1.1,
        },
        "collection_tip": "花崗岩と石灰岩の境界（スカルン帯）の川。赤〜褐色の粒状鉱物",
    },

    # ────────────────────────────────────────────────
    # 磁鉄鉱  Fe3O4
    # スカルン・接触変成岩・塩基性火山岩に産出。
    # ────────────────────────────────────────────────
    "magnetite": {
        "name_ja": "磁鉄鉱（砂鉄）",
        "name_en": "Magnetite",
        "hardness": 5.5,
        "sg": 5.2,
        "river_range_km": 100,
        "fault_bonus": 0.1,          # スカルン主体 → ×1.1
        "hydrothermal_weight": 0.4,  # スカルン・接触帯に熱水を伴う場合あり
        "color": "#2c3e50",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["スカルン"],
             "keywords_en": ["skarn"],
             "group_ja": [],
             "score": 3.0},
            {"keywords_ja": ["玄武岩", "安山岩"],
             "keywords_en": ["basalt", "andesite"],
             "group_ja": [],
             "score": 2.0},
            {"keywords_ja": [],
             "keywords_en": [],
             "group_ja": ["変成岩"],
             "score": 1.5},
        ],
        "age_bonus": {
            "白亜紀": 1.3, "Cretaceous": 1.3,
            "中新世": 1.1, "Miocene": 1.1,
        },
        "collection_tip": "砂鉄として川底の砂に濃集。磁石を使えば簡単に確認できる",
    },

    # ────────────────────────────────────────────────
    # 蛍石  CaF2
    # 熱水鉱床・スカルン・花崗岩ペグマタイトに産出。
    # ────────────────────────────────────────────────
    "fluorite": {
        "name_ja": "蛍石（フローライト）",
        "name_en": "Fluorite",
        "hardness": 4.0,
        "sg": 3.2,
        "river_range_km": 10,
        "fault_bonus": 0.4,          # 断層制御の熱水脈が多い → ×1.4
        "hydrothermal_weight": 0.8,  # 熱水脈型蛍石が主産地
        "color": "#9b59b6",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["デイサイト", "流紋岩"],
             "keywords_en": ["dacite", "rhyolite"],
             "group_ja": [],
             "score": 2.5},
            {"keywords_ja": ["花崗岩", "ペグマタイト"],
             "keywords_en": ["granite", "pegmatite"],
             "group_ja": [],
             "score": 2.0},
            {"keywords_ja": ["スカルン"],
             "keywords_en": ["skarn"],
             "group_ja": [],
             "score": 2.0},
        ],
        "age_bonus": {
            "中新世": 1.4, "Miocene": 1.4,
            "白亜紀": 1.3, "Cretaceous": 1.3,
            "古第三紀": 1.1, "Paleogene": 1.1,
        },
        "collection_tip": "断層沿いの熱水脈近傍。UV ライトで蛍光するので夜間確認も有効",
    },

    # ────────────────────────────────────────────────
    # 輝安鉱  Sb2S3
    # 低温熱水鉱床。非常に脆い → 源岩極近傍のみ。
    # ────────────────────────────────────────────────
    "stibnite": {
        "name_ja": "輝安鉱（アンチモン）",
        "name_en": "Stibnite",
        "hardness": 2.0,
        "sg": 4.6,
        "river_range_km": 3,
        "fault_bonus": 0.5,          # 低温熱水脈は強く断層制御 → ×1.5
        "hydrothermal_weight": 1.0,  # 低温熱水鉱床そのもの
        "color": "#7f8c8d",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["デイサイト", "流紋岩"],
             "keywords_en": ["dacite", "rhyolite"],
             "group_ja": [],
             "score": 2.5},
            {"keywords_ja": ["珪質"],
             "keywords_en": ["siliceous"],
             "group_ja": [],
             "score": 2.0},
            {"keywords_ja": ["付加体", "チャート"],
             "keywords_en": ["accretionary", "chert"],
             "group_ja": ["付加体"],
             "score": 1.5},
        ],
        "age_bonus": {
            "中新世": 1.5, "Miocene": 1.5,
            "鮮新世": 1.3, "Pliocene": 1.3,
        },
        "collection_tip": "断層・熱水変質帯の直近のみ。銀白色・金属光沢の針状結晶を探す",
    },

    # ────────────────────────────────────────────────
    # 菱マンガン鉱  MnCO3
    # マンガン熱水鉱床に産出。美しいピンク〜赤色。
    # ────────────────────────────────────────────────
    "rhodochrosite": {
        "name_ja": "菱マンガン鉱",
        "name_en": "Rhodochrosite",
        "hardness": 3.5,
        "sg": 3.7,
        "river_range_km": 5,
        "fault_bonus": 0.4,          # Mn 熱水脈は断層制御が多い → ×1.4
        "hydrothermal_weight": 0.8,  # Mn 熱水鉱床に強く依存
        "color": "#e91e8c",
        "marker": "circle",
        "tiers": [
            {"keywords_ja": ["デイサイト", "流紋岩"],
             "keywords_en": ["dacite", "rhyolite"],
             "group_ja": [],
             "score": 2.5},
            {"keywords_ja": ["安山岩"],
             "keywords_en": ["andesite"],
             "group_ja": [],
             "score": 2.0},
            {"keywords_ja": ["珪質"],
             "keywords_en": ["siliceous"],
             "group_ja": [],
             "score": 1.5},
        ],
        "age_bonus": {
            "中新世": 1.5, "Miocene": 1.5,
            "鮮新世": 1.3, "Pliocene": 1.3,
        },
        "collection_tip": "Mn熱水鉱床近傍の川。ピンク〜赤色の菱形劈開を持つ塊状鉱物",
    },
}

# 地図表示時のデフォルト選択鉱物
DEFAULT_MINERALS = ["opal", "gold", "jade", "quartz", "garnet"]
