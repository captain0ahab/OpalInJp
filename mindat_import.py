#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mindat.org API から日本の産地データを取得して KNOWN_LOCALITIES 形式に出力する

APIキー取得手順:
  1. https://www.mindat.org/ でアカウント登録（無料）
  2. https://www.mindat.org/a/mindat_api → "Get API Key"
  3. py mindat_import.py --key <YOUR_KEY>
  4. 出力された mindat_localities.py を確認し、score_extras.py に追記

使い方:
  py mindat_import.py --key <YOUR_KEY>             # 全鉱物を取得
  py mindat_import.py --key <YOUR_KEY> --dry-run   # APIテスト・件数確認のみ
  py mindat_import.py --key <YOUR_KEY> --mineral gold  # 特定鉱物のみ
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.mindat.org"
DELAY = 0.8   # リクエスト間隔（秒）。レート制限対策

# プロジェクトの鉱物キー → Mindat での検索鉱物名
# 複数指定した場合は全て取得してマージする
MINERAL_MAP = {
    "opal":          ["Opal", "Hyalite"],
    "gold":          ["Gold"],
    "jade":          ["Jadeite"],
    "quartz":        ["Quartz"],
    "garnet":        ["Almandine", "Pyrope", "Spessartine", "Grossular", "Andradite"],
    "magnetite":     ["Magnetite"],
    "fluorite":      ["Fluorite"],
    "stibnite":      ["Stibnite"],
    "rhodochrosite": ["Rhodochrosite"],
}

# 都道府県名 → 英語表記（Mindatの産地名からパースするため）
PREFECTURES = [
    "Hokkaido", "Aomori", "Iwate", "Miyagi", "Akita", "Yamagata", "Fukushima",
    "Ibaraki", "Tochigi", "Gunma", "Saitama", "Chiba", "Tokyo", "Kanagawa",
    "Niigata", "Toyama", "Ishikawa", "Fukui", "Yamanashi", "Nagano", "Shizuoka",
    "Aichi", "Mie", "Shiga", "Kyoto", "Osaka", "Hyogo", "Nara", "Wakayama",
    "Tottori", "Shimane", "Okayama", "Hiroshima", "Yamaguchi",
    "Tokushima", "Kagawa", "Ehime", "Kochi",
    "Fukuoka", "Saga", "Nagasaki", "Kumamoto", "Oita", "Miyazaki", "Kagoshima",
    "Okinawa",
]


# ─────────────────────────────────────────────
# API ユーティリティ
# ─────────────────────────────────────────────

def api_get(path, params, token):
    """Mindat API への GET リクエスト。失敗時は None を返す。"""
    qs = urllib.parse.urlencode({**params, "format": "json"})
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Token {token}",
        "User-Agent": "OpalInJp/1.0 (https://github.com/captain0ahab/OpalInJp)",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if e.code == 401:
            sys.exit("APIキーが無効または期限切れです。https://www.mindat.org/a/mindat_api で確認してください。")
        if e.code == 429:
            print(f"  レート制限に達しました。{DELAY*3:.0f}秒待機...", file=sys.stderr)
            time.sleep(DELAY * 3)
            return None
        print(f"  HTTP {e.code}: {url}\n  {body[:300]}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"  接続エラー: {e.reason}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"  JSONパースエラー: {e}", file=sys.stderr)
        return None


def paginate(path, params, token, max_pages=50, label=""):
    """ページネーションを処理して全件リストで返す。"""
    results = []
    p = dict(params, page_size=100, page=1)
    for i in range(1, max_pages + 1):
        data = api_get(path, p, token)
        if not data:
            break
        batch = data.get("results", [])
        results.extend(batch)
        total = data.get("count", "?")
        if label and i == 1:
            print(f"    全{total}件 → ページ取得中", end="", flush=True)
        if label:
            print(".", end="", flush=True)
        if not data.get("next"):
            break
        p["page"] += 1
        time.sleep(DELAY)
    if label:
        print(f" {len(results)}件取得")
    return results


# ─────────────────────────────────────────────
# Mindat データ解析
# ─────────────────────────────────────────────

def get_mineral_id(name, token):
    """鉱物名（英語）から Mindat の geomaterial ID を返す。"""
    data = api_get("/geomaterials/", {"name": name}, token)
    if not data:
        return None
    for item in data.get("results", []):
        if item.get("name", "").strip().lower() == name.lower():
            return item["id"]
    # 完全一致しない場合は前方一致で最初のものを返す
    results = data.get("results", [])
    if results:
        return results[0]["id"]
    return None


def parse_locality(result):
    """
    localitymineral または localities レスポンスから
    (lat, lon, name, country) を取り出す。
    Mindat のレスポンス構造が変わっても壊れにくいよう複数フィールドを試す。
    """
    loc = result.get("locality") or result

    lat = (loc.get("latitude")
           or loc.get("lat")
           or loc.get("declatitude"))
    lon = (loc.get("longitude")
           or loc.get("lon")
           or loc.get("declongitude"))
    name = (loc.get("name")
            or loc.get("locality_name")
            or loc.get("longname", ""))
    country = str(
        loc.get("country_str")
        or loc.get("country")
        or loc.get("country_name")
        or ""
    ).lower()

    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None

    return lat, lon, name.strip(), country


def infer_confidence(locality_name, mindat_result):
    """
    産地名・属性から信頼度 1〜3 を推定する。
    - 3: 有名な mine / 鉱山
    - 2: 明確な地名あり
    - 1: 地域のみ（県レベルなど）
    """
    name_lower = locality_name.lower()
    if any(w in name_lower for w in ("mine", "mining", "鉱山", "坑", "quarry")):
        return 3
    for pref in PREFECTURES:
        if pref.lower() in name_lower:
            # 都道府県名だけの場合は信頼度1
            if len(locality_name) < len(pref) + 12:
                return 1
            return 2
    return 2


def build_note(mindat_name, mindat_mineral_name):
    """備考文字列を生成する。"""
    return f"Mindat産地: {mindat_name} ({mindat_mineral_name})"


# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def fetch_for_mineral(our_key, mindat_names, token, dry_run=False):
    """1鉱物分の日本産地を全て取得して返す。"""
    entries = []
    seen_coords = set()

    for mname in mindat_names:
        print(f"  [{mname}] ID検索...", end=" ", flush=True)
        mid = get_mineral_id(mname, token)
        if mid is None:
            print("IDが見つかりませんでした。スキップ。")
            continue
        print(f"id={mid}")
        time.sleep(DELAY)

        if dry_run:
            data = api_get("/localitymineral/", {"mineral": mid, "page_size": 1}, token)
            count = data.get("count", "?") if data else "?"
            print(f"    産地数（全世界）: {count}件")
            continue

        # 日本限定でサーバーサイドフィルタを試みる（サポートされていない場合はクライアント側でフィルタ）
        results = paginate(
            "/localitymineral/",
            {"mineral": mid},
            token,
            label=mname,
        )

        jp_count = 0
        for r in results:
            lat, lon, name, country = parse_locality(r)
            if "japan" not in country:
                continue
            if lat is None or lon is None or not name:
                continue
            # 座標の重複除去（小数点2桁で丸めて比較）
            coord_key = (round(lat, 2), round(lon, 2))
            if coord_key in seen_coords:
                continue
            seen_coords.add(coord_key)

            confidence = infer_confidence(name, r)
            note = build_note(name, mname)
            entries.append((name, lat, lon, confidence, note))
            jp_count += 1

        print(f"    → 日本産地: {jp_count}件")
        time.sleep(DELAY)

    return entries


def format_output(all_entries):
    """KNOWN_LOCALITIES 追記用の Python コードを返す。"""
    lines = ["# Mindat.org から取得した追加産地データ"]
    lines.append("# score_extras.py の KNOWN_LOCALITIES に各鉱物リストへ追記してください\n")

    for our_key, entries in all_entries.items():
        if not entries:
            continue
        lines.append(f'    # --- Mindat 追加: {our_key} ---')
        for name, lat, lon, conf, note in entries:
            # 文字列のシングルクォートをエスケープ
            safe_name = name.replace("'", "\\'")
            safe_note = note.replace("'", "\\'")
            lines.append(
                f'    ("{safe_name}", {lat:.4f}, {lon:.4f}, {conf}, "{safe_note}"),'
            )
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Mindat.org から日本の鉱物産地データを取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--key", required=True, help="Mindat API キー")
    parser.add_argument("--dry-run", action="store_true",
                        help="APIの疎通確認と件数表示のみ（データ保存なし）")
    parser.add_argument("--mineral", default="all",
                        help=f"取得する鉱物（all または {'/'.join(MINERAL_MAP)}）")
    parser.add_argument("--out", default="mindat_localities.py",
                        help="出力ファイル名（デフォルト: mindat_localities.py）")
    args = parser.parse_args()

    token = args.key.strip()

    # 対象鉱物を決定
    if args.mineral == "all":
        targets = MINERAL_MAP
    elif args.mineral in MINERAL_MAP:
        targets = {args.mineral: MINERAL_MAP[args.mineral]}
    else:
        sys.exit(f"不明な鉱物名: {args.mineral}。指定可能: {', '.join(MINERAL_MAP)}")

    # API 疎通確認
    print("Mindat API 接続確認...", end=" ", flush=True)
    test = api_get("/geomaterials/", {"name": "Gold", "page_size": 1}, token)
    if not test:
        sys.exit("API接続失敗。キーとネット接続を確認してください。")
    print(f"OK（geomaterials count={test.get('count', '?')}）\n")

    if args.dry_run:
        print("=== DRY RUN: 件数確認のみ ===\n")

    all_entries = {}
    for our_key, mnames in targets.items():
        print(f"■ {our_key}")
        entries = fetch_for_mineral(our_key, mnames, token, dry_run=args.dry_run)
        all_entries[our_key] = entries
        print()

    if args.dry_run:
        print("=== DRY RUN 完了。--dry-run を外すと実際にデータを取得します ===")
        return

    # 結果サマリ
    total = sum(len(v) for v in all_entries.values())
    print(f"\n=== 取得完了: 日本産地 合計 {total} 件 ===")
    for k, v in all_entries.items():
        print(f"  {k:20s}: {len(v):4d} 件")

    if total == 0:
        print("\n産地データが取得できませんでした。APIレスポンス構造が変わっている可能性があります。")
        print("--dry-run で件数を確認し、スクリプト内の parse_locality() を調整してください。")
        return

    # ファイル出力
    out_path = Path(args.out)
    out_path.write_text(format_output(all_entries), encoding="utf-8")
    print(f"\n→ {out_path} に保存しました。")
    print("  内容を確認後、score_extras.py の KNOWN_LOCALITIES に追記してください。")
    print("\n追記の際は座標が既存エントリと重複していないか確認することをお勧めします。")


if __name__ == "__main__":
    main()
