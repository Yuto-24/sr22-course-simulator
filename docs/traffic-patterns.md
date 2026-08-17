# Airport Traffic-Pattern Reference Paths

## 対象

第一段階として、宮崎空港 RJFM の4本の Normal Traffic Pattern を生成します。

- RWY09 NORTH / SOUTH
- RWY27 NORTH / SOUTH

生成物は aircraft dynamics や wind correction を含む `Trajectory` ではありません。空港・滑走路データと運用資料の寸法から構成した、風に依存しない `PolylineReferencePath` です。

## 幾何基準

ARP は空港の reference point であり、滑走路中心線上にあるとは限りません。このため pattern geometry には使わず、原資料の表示と sanity check にだけ使います。

各方向の滑走路幾何は次の点を原点にします。

```text
RWY Center Point = (threshold_a + threshold_b) / 2
```

`RunwaySpec.true_bearing_deg` から runway vector を作り、その left / right normal を downwind 方向に使います。すべての waypoint は RWY Center Point からの along-runway / lateral displacement として決定します。緯度・経度の hard-code は canonical threshold data だけに限定されます。

KML の幾何計算は True Bearing です。Magnetic Variation は `AirportSpec.variation_at()` と `true_to_magnetic()` で表示・検算できますが、Reference Path には入りません。符号は East positive / West negative です。

## RJFM master data

`src/sr22_course_simulator/data/airports/rjfm.py` は、タスクで提供された `RJFM__20260301.pdf` の転記値を保持します。PDF 自体は repository に含まれていないため、provenance の extraction method は `task-provided transcription` としています。

Airport data:

- ARP: `315238N`, `1312655E`（参照用のみ）
- AD elevation: 19 ft
- MAG VAR: 2020年 -7.0°、annual change -5 arcmin/year

Runway data:

- RWY09 True Bearing 85.18°、threshold `315234.26N`, `1312607.02E`
- RWY27 True Bearing 265.18°、threshold `315241.06N`, `1312741.80E`
- declared dimensions: 2500 m × 45 m

compact DMS は `parse_aip_dms()` で decimal degree に変換します。将来の RJFO / RJFK / RJFT / RJFS / RJFU / RJFG / RJFC も同じ `AirportSpec` / `RunwaySpec` へ格納し、派生値は deterministic に計算します。

## Pattern geometry

既定値は次のとおりです。

| 項目 | 値 | 意味 |
| --- | ---: | --- |
| Pattern altitude | 1000 ft MSL | 全点固定。vertical profile なし |
| Downwind offset | 1.5 NM | runway centerline に直角 |
| Base extension | 1.2 NM | landing threshold から approach 側 |
| Crosswind extension | 0.0 NM | departure end からの延長。明示的仮定 |

各 path は straight segment だけで構成します。

```text
departure_reference
  -> crosswind
  -> downwind
  -> base
  -> final
  -> threshold_return
```

`crosswind_extension_nm = 0.0` では `departure_reference` が reciprocal threshold / departure end に一致します。正の値では runway true-bearing 方向へ延長します。turn radius、climb / descent、wind、guidance、aircraft dynamics はこのモデルの範囲外です。

## Notebook と KML

`notebooks/miyazaki_traffic_patterns.ipynb` を上から実行すると、master data、threshold、RWY Center Point、pattern parameters を表示し、4 path を可視化して次へ出力します。

```text
artifacts/traffic-patterns/
├── RJFM_RWY09_NORTH.kml
├── RJFM_RWY09_SOUTH.kml
├── RJFM_RWY27_NORTH.kml
├── RJFM_RWY27_SOUTH.kml
└── RJFM_ALL_NORMAL_PATTERNS.kml
```

CLI からも同じ処理を実行できます。

```bash
PYTHONPATH=src python3 -m sr22_course_simulator.examples.miyazaki_traffic_patterns
```

個別ファイルは `reference_path_to_kml()`、結合ファイルは `reference_paths_to_kml()`、書き込みは共通の `write_kml()` を使用します。
