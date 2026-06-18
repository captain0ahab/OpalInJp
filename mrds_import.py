#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USGS MRDS (Mineral Resources Data System) から日本の鉱床データを取得して
score_extras.py の KNOWN_LOCALITIES 形式に変換するスクリプト

データソース: https://mrdata.usgs.gov/mrds/
ライセンス: Public Domain (U.S. Government Work)
認証: 不要（完全無料・無登録）

使い方:
  py mrds_import.py              # 全鉱物を取得して mrds_localities.py に出力
  py mrds_import.py --dry-run   # 件数確認のみ
  py mrds_import.py --preview   # 取得データを画面表示のみ
"""

import argparse
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

WFS_URL = "https://mrdata.usgs.gov/services/wfs/mrds"

# 日本の広域 bounding box (lon_min, lat_min, lon_max, lat_max)
# 沖縄〜北海道をカバー
JAPAN_BBOX = "122,24,154,46"

# USGS MRDS 商品コード → プロジェクトの鉱物キー
# MRDS は鉱山データ中心のため採集系鉱物（翡翠・ザクロ石等）は少ない
COMMODITY_MAP = {
    "AU":   "gold",        # Gold（金）
    "AG":   "gold",        # Silver（銀）→ 金銀鉱山として gold に含める
    "SB":   "stibnite",    # Antimony（アンチモン）= 輝安鉱
    "MN":   "rhodochrosite",  # Manganese（マンガン）= 菱マンガン鉱
    "MAG":  "magnetite",   # Magnetite（磁鉄鉱）
    "FE":   "magnetite",   # Iron（鉄）= 磁鉄鉱
    "F":    "fluorite",    # Fluorite（蛍石）
    "FL":   "fluorite",    # Fluorite（別表記）
    "OP":   "opal",        # Opal（オパール）
    "QRTZ": "quartz",      # Quartz（水晶）
    "QTZ":  "quartz",
    "GAR":  "garnet",      # Garnet（ザクロ石）
    "GEM":  "jade",        # Gemstone（翡翠等の宝石）
    "JD":   "jade",        # Jade（翡翠）
}

# dev_stat → 信頼度マッピング
DEV_STAT_CONFIDENCE = {
    "Producer":        3,
    "Past Producer":   3,
    "Occurrence":      2,
    "Prospect":        2,
    "Plant":           2,
    "Mine":            3,
}

NS = {
    "wfs": "http://www.opengis.net/wfs",
    "ms":  "http://mapserver.gis.umn.edu/mapserver",
    "gml": "http://www.opengis.net/gml",
}


def fetch_wfs(bbox, max_features=500, start_index=0):
    """USGS MRDS WFS から GML 取得"""
    params = {
        "service":     "WFS",
        "version":     "1.0.0",
        "request":     "GetFeature",
        "typeName":    "mrds",
        "BBOX":        bbox,
        "maxFeatures": max_features,
    }
    url = WFS_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "OpalInJp/1.0 (https://github.com/captain0ahab/OpalInJp)",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8")
    except urllib.error.URLError as e:
        print(f"接続エラー: {e.reason}", file=sys.stderr)
        return None


def parse_gml(gml_text):
    """GML レスポンスを解析してレコードのリストを返す"""
    try:
        root = ET.fromstring(gml_text)
    except ET.ParseError as e:
        print(f"XMLパースエラー: {e}", file=sys.stderr)
        return []

    records = []
    for member in root.findall(".//gml:featureMember", NS):
        mrds = member.find("ms:mrds", NS)
        if mrds is None:
            continue

        fips = (mrds.findtext("ms:fips_code", "", NS) or "").strip()
        if "JA" not in fips:
            continue

        # 座標 (lon,lat 形式)
        coords_el = mrds.find(".//gml:Point/gml:coordinates", NS)
        if coords_el is None or not coords_el.text:
            continue
        try:
            lon_str, lat_str = coords_el.text.strip().split(",")[:2]
            lon = float(lon_str)
            lat = float(lat_str)
        except (ValueError, IndexError):
            continue

        # 日本の範囲外はスキップ（bbox に韓国等が混入する場合がある）
        if not (24 <= lat <= 46 and 122 <= lon <= 154):
            continue

        name     = (mrds.findtext("ms:site_name",  "", NS) or "").strip()
        dev_stat = (mrds.findtext("ms:dev_stat",   "", NS) or "").strip()
        code_raw = (mrds.findtext("ms:code_list",  "", NS) or "").strip()
        url      = (mrds.findtext("ms:url",        "", NS) or "").strip()

        codes = [c.strip() for c in code_raw.upper().split() if c.strip()]

        records.append({
            "name":     name,
            "lat":      lat,
            "lon":      lon,
            "codes":    codes,
            "dev_stat": dev_stat,
            "url":      url,
        })

    return records


def is_facility(rec):
    """精錬所・処理施設など地質的産地でないエントリを除外"""
    name_lower = rec["name"].lower()
    # 精錬所・製錬所・工場
    if name_lower.startswith("(facility)"):
        return True
    if any(w in name_lower for w in ("refinery", "smelter", "plant", "works")):
        return True
    # dev_stat が Plant で名前に facility 系ワードがあるもの
    if rec["dev_stat"] == "Plant" and any(w in name_lower for w in ("dept", "division", "co.", "corp")):
        return True
    return False


def map_to_minerals(records):
    """MRDS レコードを鉱物キーごとに分類"""
    mineral_entries = {k: [] for k in set(COMMODITY_MAP.values())}
    seen = {}  # mineral_key → set of (rounded lat, rounded lon)
    for k in mineral_entries:
        seen[k] = set()

    for rec in records:
        if is_facility(rec):
            continue

        matched = set()
        for code in rec["codes"]:
            mineral_key = COMMODITY_MAP.get(code)
            if mineral_key:
                matched.add(mineral_key)

        for mk in matched:
            coord_key = (round(rec["lat"], 2), round(rec["lon"], 2))
            if coord_key in seen[mk]:
                continue
            seen[mk].add(coord_key)

            confidence = DEV_STAT_CONFIDENCE.get(rec["dev_stat"], 2)
            codes_str  = " ".join(rec["codes"])
            note       = f"USGS MRDS: {rec['dev_stat']} [{codes_str}]"

            mineral_entries[mk].append({
                "name":       rec["name"],
                "lat":        rec["lat"],
                "lon":        rec["lon"],
                "confidence": confidence,
                "note":       note,
                "url":        rec["url"],
            })

    return mineral_entries


def format_output(mineral_entries):
    """score_extras.py から import できる Python モジュールを生成"""
    lines = [
        "# -*- coding: utf-8 -*-",
        "# USGS MRDS (Mineral Resources Data System) 日本産地データ",
        "# https://mrdata.usgs.gov/mrds/ (Public Domain)",
        "# このファイルは mrds_import.py で自動生成されます。手動編集しないでください。",
        "# score_extras.py が自動的に読み込んで KNOWN_LOCALITIES にマージします。",
        "",
        "MRDS_LOCALITIES = {",
    ]
    for mk, entries in mineral_entries.items():
        if not entries:
            continue
        lines.append(f'    "{mk}": [')
        lines.append(f'        # {len(entries)}件 - USGS MRDS')
        for e in entries:
            safe_name = e["name"].replace('"', '\\"')
            safe_note = e["note"].replace('"', '\\"')
            lines.append(
                f'        ("{safe_name}", {e["lat"]:.4f}, {e["lon"]:.4f},'
                f' {e["confidence"]}, "{safe_note}"),'
            )
        lines.append("    ],")
    lines.append("}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="USGS MRDS から日本の鉱床データを取得（認証不要）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="件数確認のみ（ファイル出力なし）")
    parser.add_argument("--preview", action="store_true",
                        help="データを画面表示（ファイル出力なし）")
    parser.add_argument("--out", default="mrds_localities.py",
                        help="出力ファイル名（デフォルト: mrds_localities.py）")
    args = parser.parse_args()

    print("USGS MRDS WFS から日本の鉱床データを取得中...")
    print(f"  エンドポイント: {WFS_URL}")
    print(f"  対象エリア: 日本全域 (bbox={JAPAN_BBOX})\n")

    gml = fetch_wfs(JAPAN_BBOX, max_features=1000)
    if not gml:
        sys.exit("データ取得に失敗しました。")

    records = parse_gml(gml)
    print(f"取得レコード数（日本）: {len(records)} 件\n")

    if not records:
        print("日本のデータが取得できませんでした。")
        print("WFSエンドポイントの仕様が変更された可能性があります。")
        sys.exit(1)

    if args.dry_run:
        # 商品コードの分布を表示
        from collections import Counter
        all_codes = []
        for r in records:
            all_codes.extend(r["codes"])
        code_counts = Counter(all_codes).most_common(30)
        print("=== 商品コード分布（日本）===")
        for code, cnt in code_counts:
            mapped = COMMODITY_MAP.get(code, "（未対応）")
            print(f"  {code:8s} {cnt:4d}件  → {mapped}")
        print(f"\n対応済みコードの産地: {sum(1 for r in records if any(COMMODITY_MAP.get(c) for c in r['codes']))} 件")
        return

    mineral_entries = map_to_minerals(records)

    total = sum(len(v) for v in mineral_entries.values())
    print("=== 鉱物別産地数 ===")
    for mk, entries in mineral_entries.items():
        if entries:
            print(f"  {mk:20s}: {len(entries):4d} 件")
    print(f"  合計: {total} 件\n")

    if args.preview:
        for mk, entries in mineral_entries.items():
            if not entries:
                continue
            print(f"■ {mk}")
            for e in entries:
                print(f"  {e['name']:40s}  lat={e['lat']:.4f} lon={e['lon']:.4f}  [{e['note']}]")
            print()
        return

    out_path = Path(args.out)
    out_path.write_text(format_output(mineral_entries), encoding="utf-8")
    print(f"→ {out_path} に保存しました。")
    print("  内容を確認後、score_extras.py の KNOWN_LOCALITIES に追記してください。")
    print("\n  既存エントリとの座標重複確認を推奨します（小数点2桁で自動除去済み）。")


if __name__ == "__main__":
    main()
