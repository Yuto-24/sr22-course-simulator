# Airport Traffic Pattern and Independent Turn Reference Paths

## 対象とモデル境界

`TrafficPatternSpec` は空港・滑走路方向・LEFT/RIGHTごとに運用値を保持します。現在の完成済みの空港別 generator は宮崎空港 RJFM の4本です。その他7空港の運用profileとKML一括生成はIssue #9で追加します。

- RWY09 LEFT / RIGHT
- RWY27 LEFT / RIGHT

各RWY／LEFT・RIGHTについて、Aiming Markerから同じAiming Markerへ戻る通常場周本体と、選択したCircle／270を別々の`PolylineReferencePath`として生成します。通常場周本体へCircleや270を連結しないため、KMLでは各Placemarkを独立して表示できます。110 KTAS、Bank、Roll rateは曲線形状を構築する入力であり、出力はwindやtime-indexed aircraft dynamicsを含む`Trajectory`ではありません。

## Identity、運用profile、airport loader

Canonical identityは `ICAO + RWY + LEFT/RIGHT` です。`PatternLabel` と `TrafficPatternSpec.label` は削除しました。方位名は設定key・path名・filenameに使用しません。RJFMの移行は09 NORTH→LEFT、09 SOUTH→RIGHT、27 NORTH→RIGHT、27 SOUTH→LEFTです。Notebook/CLIは同じAPIを使用し、生成名のみこのidentityへ移行します。

新しいprofileクラスは追加せず、既存の`TrafficPatternSpec`に`descent_start`、`preferred`、`notes`を追加しました。既存の`altitude_ft`、`downwind_offset_nm`、`crosswind_base_extension_nm`と合わせて、RWY×LEFT/RIGHT単位で指定できます。`source`はその運用profileの出典です。`preferred`と`notes`はmetadataのみで、反対側の生成を禁止しません。RJFMは既存の宮崎訓練飛行実施要領の北側通常使用に対応して、09 LEFTと27 RIGHTを`preferred=True`とします。

```python
from sr22_course_simulator.data.airports import load_airport
from sr22_course_simulator.path import DescentStart, PatternSide, TrafficPatternSpec

airport = load_airport("RJFT")
# sourceには当該RWY/sideの運用値を裏付けるSourceCitationを渡す。
# spec = TrafficPatternSpec(
#     airport=airport, runway=airport.runway("07"), side=PatternSide.LEFT,
#     altitude_ft=1400, downwind_offset_nm=1.5,
#     crosswind_base_extension_nm=1.5, source=source,
#     descent_start=DescentStart.BASE_TURN_END,
# )
```

`load_airport(icao)`はbundled canonical JSONからRJFC/RJFG/RJFK/RJFM/RJFO/RJFS/RJFT/RJFUを読み込みます。AIP値をPythonへ再転記せず、`AirportSpec.source`はAD 2.2、各`RunwaySpec.source`はAD 2.12のdocument、section、effective date、page、PDF SHA-256を保持します。PDFファイル名の日付で節ごとの有効日を上書きしません。RJFMの数値は旧Python転記と同一ですが、runwayの出典有効日はcanonical記載の2025-05-15です。

現行loaderのsource domainは各空港1本の物理滑走路と2方向です。未知空港、必須データ欠落、複数滑走路のpairing未定義は不足field/relationshipを示す`ValidationError`です。ARPやMagnetic Variationから不足値を補完しません。

## 幾何基準

ARPは参照・検算専用です。すべての座標は次のRWY Center PointとTrue Bearingから作ります。

```text
RWY Center Point = (threshold_a + threshold_b) / 2
```

Magnetic Variationは表示・検算にだけ使い、KML座標やReferencePathへは使用しません。

通常場周の骨格は、先に固定します。

- Downwind axisはRWY Center Pointから場周外側へ1.5 NMです。
- Crosswind/Base axisは各THRから滑走路延長方向へ1.2 NMです。
- したがって、一方向のCrosswind axisと反対方向のBase axisは同じ物理線です。

各turnはこの骨格へ接線接続するため、Circle／270の表示有無やRoll遷移で通常場周のLeg axisは移動しません。通常場周本体は常にCircle／270なしの22° 90° turnで固定し、KMLの第1 Placemarkも全32設定で同一です。

## 旋回条件

API既定値は次のとおりです。Notebookのparameter cellは保存済みの作業設定を表示するため、ここでの既定値とは別に値を持つことがあります。

| 項目 | 値 | 意味 |
| --- | ---: | --- |
| 定常速度 | 110 KTAS | 旋回半径と旋回率の計算速度 |
| Normal Bank | 30° | Upwind→Crosswind turn |
| Circle／270 Bank | 22° | すべてのMake CircleとBefore Downwind/Baseの270° turn（110 KTAS・10°/s Rollと共有） |
| Ordinary Downwind Bank | 22° | 通常場周本体の90° Downwind turn |
| Ordinary Base Bank | 22° | 通常場周本体の90° Base Turn |
| Final Bank | 25° | BaseからFinalへの90° turn |
| Roll rate | 10°/s | 各turnの線形Roll in/out |
| Sample interval | 0.25 s | 曲線の決定論的sampling |
| Before Downwind Make Circle | ON | 独立した外側360° Pathを追加 |
| Make 270 Before Downwind | ON | 独立した外側270° Pathを追加 |
| Middle Downwind Make Circle | ON | ON: 360°、OFF: 直進 |
| Before Base Make Circle | OFF | 独立した外側360° Pathを追加 |
| Make 270 Before Base | ON | 独立した外側270° Pathを追加 |

定常旋回半径はcoordinated-turnの関係から求めます。

```text
R = V² / (g tan Bank)
```

110 KTASでは、30° Bankが約565.59 m（0.305 NM）、25° Bankが約700.28 m（0.378 NM）、22° Bankが約808.22 m（0.436 NM）です。Roll区間はBankを時間に対して線形に変え、瞬間旋回率`g tan(Bank) / V`を積分します。22° BankのMiddle Downwind 360°はRoll-in/outも積分するため開始点へ厳密には戻らず、Downwind進行方向へ約127.62 m進む`physics_derived`な挙動です。

通常場周本体の経路順序は次のとおりです。

1. Aiming MarkerからTakeoff/Upwindを進み、Upwind→Crosswind：場周方向へ90°。
2. Before Downwind：110 KTAS・22° Bankの通常90° Downwind turn。全区間1,000 ft MSLを維持します。
3. Middle Downwind：Circleを組み込まず直進します。
4. Before Base：110 KTAS・22° Bankの通常90° Base Turnへ入り、その開始と同時に降下します。
5. Base→Final：場周方向へ90°、25° Bank。
6. Final：3° pathでthresholdを通過し、Aiming Markerへ到達します。

Left Trafficの外側turnはRight、Right TrafficではLeftです。仮想コーナーの手前または先へturn開始点をずらし、Roll遷移を含む曲線を既存のCrosswind、Downwind、Base、Final各axisへ接線接続します。

追加PathはBefore Downwind Circle、Before Downwind 270、Middle Downwind Circle、Before Base Circle、Before Base 270の最大5本です。各Booleanは独立しており、Circle ON／270 OFFを含む32通りすべてが有効です。Circleは360°、270は270°だけを持ち、従来の630°（360°+270°）へ結合しません。

Before Downwind／Before BaseのCircleは、270のON/OFFにかかわらず同じ潜在270° turnを内部計算し、その`before_*_turn_start`座標と進入Headingから始めます。Circleには接続線を含めません。対応する270 Placemarkは、通常場周の`before_*_branch`から同軸の進入接続線、270° arc（既存の`before_*_turn_start`から`before_*_turn_end`）、同軸の退出接続線、`before_*_merge`までを連続して含みます。branch／mergeは通常場周の22° turnの開始／終了座標と完全に一致します。

単一の連続経路を返す`generate_traffic_pattern()`では、Circle ON／270 OFFの場合、360° Circleの終了点を通常90° turnの開始点へ合わせ、その後に通常turnを続けます。Roll遷移によるCircleの前進量も含めて終点合わせし、leg axisと接線を維持します。共有点は`before_*_turn_end`、通常turnの終了点は`downwind_turn_end`／`base_turn_end`です。独立component APIのCircleは引き続き潜在270の開始点に配置します。

## 降下開始のsemantic

`DescentStart`は次の3種類です。Circle/270のBooleanはprofileを変更しません。

| 値 | 通常場周の降下開始 |
| --- | --- |
| `ABEAM_THRESHOLD` | Downwind axis上のlanding-threshold station (`abeam_threshold`) |
| `BASE_TURN_START`（既定） | 通常90° Base turn開始 (`base_turn_start`) |
| `BASE_TURN_END` | 通常90° Base turnの実際のrollout (`base_turn_end`) |

`abeam_threshold`は既存の直線を分割するsemantic vertexで、通常場周の水平形状は変えません。単一経路APIではCircle/270内部の横切りをAbeamと取り違えません。要求したAbeamが直線Downwind上に存在しない組合せは、必要なstraight-Downwind/threshold-station relationshipを示すmodel gapになります。

単一経路APIの`BASE_TURN_START`はPR #7の対応を維持します。270ありでは`before_base_turn_start`、Circle-onlyではCircle終了・通常90°開始の共有点`before_base_turn_end`、両方OFFでは`base_turn_start`です。`BASE_TURN_END`は270ありでは`before_base_turn_end`、それ以外はCircleの終了点ではなく通常90°の`base_turn_end`です。

独立component APIでは常に同じ通常場周を第1 pathにします。追加Circleは従来どおり場周高度で独立表示する比較用pathであり、降下中の経路へ連結する飛行指令ではありません。Abeam指定のBefore Base 270は、既に降下している通常場周のbranch高度からmerge高度まで代替経路距離に比例して接続します。この追加距離に対する勾配は明示的な幾何近似です。通常場周のAbeam位置や高度は変えません。

`BASE_TURN_END`のBefore Base 270は実際の270 rolloutまで場周高度を維持し、そこから降下します。そのrolloutは通常90°のBase終点より外側にあります。通常Base終点はまだ場周高度なので、そこへ高度まで再合流すると途中の降下を取り消す上昇が必要になります。そのため、このprofileの270 pathだけは既存のBase/Final形状をFinal rolloutまで含め、そこで通常場周に高度まで合流します。`before_base_merge`は水平合流点、`final_turn_end`は3D合流点です。この関係はcomponent citationにも保持します。Circle/270の旋回数学は変更しません。

## 高度（既定のRJFM profile）

- Aiming Markerの滑走路面MSL標高からUpwind turn開始点の1,000 ft MSLまで、Upwind距離に比例して上昇します。
- Upwind turn開始から降下対象turnの開始までは1,000 ft MSLです。
- 通常場周本体は通常Base Turnの開始から、Final rolloutまで経路距離に比例して3° Finalへの接続高度まで降下します。
- Circle PathとBefore Downwind 270 Pathは全区間1,000 ft MSLを維持します。単一経路APIのBefore Base Circle-onlyもCircle中は場周高度を維持し、`before_base_turn_end`（通常90° Base Turnとの共有点）から降下します。270を含む単一経路は従来どおり`before_base_turn_start`から降下します。
- Before Base 270 Pathは、通常22° Base Turnの水平polyline沿程長を基準にします。代替Pathのmergeからその距離を正確に逆算した`before_base_descent_start`までは1,000 ft MSLを維持し、そこから`before_base_merge`まで水平沿程距離に比例して降下します。merge高度は通常`base_turn_end`と完全に一致します。代替Pathがこの基準長より短い場合は`ValidationError`です。
- Final rollout以降はAiming Markerを0 ft AGLとする3° pathです。
- 滑走路長が2,400 m以上ならAiming MarkerはTHRから400 m、その他は300 mです。
- KMLのabsolute altitudeへ変換するため、Aiming Markerの滑走路面MSL標高は両threshold標高から線形補間します。

経路には`landing_threshold`と`aiming_marker`を別々のsemantic pointとして残します。

## Notebook、CLI、KML

`notebooks/miyazaki_traffic_patterns.ipynb`では全パラメータ、計算半径、通常場周と独立Circle／270の平面図、KML出力を順に確認できます。CLIでも同じ生成処理を実行できます。

Notebookでは次のBooleanを変更します。値はユーザーが保存したNotebook設定をそのまま使用します。

```python
MAKE_CIRCLE_BEFORE_DOWNWIND = True
MAKE_270_BEFORE_DOWNWIND = True
MAKE_CIRCLE_MIDDLE_DOWNWIND = True
MAKE_CIRCLE_BEFORE_BASE = True
MAKE_270_BEFORE_BASE = True
```

5個のBooleanは相互依存しません。ONにしたPathだけが通常場周本体とは別のPlacemarkとしてKMLへ追加されます。

```bash
PYTHONPATH=src python3 -m sr22_course_simulator.examples.miyazaki_traffic_patterns
```

CLIでは各 `--make-circle-*` / `--no-make-circle-*` とBefore Downwind/Baseの `--make-270-*` / `--no-make-270-*` を使用できます。例としてすべてをOFFにする場合は次のとおりです。

```bash
PYTHONPATH=src python3 -m sr22_course_simulator.examples.miyazaki_traffic_patterns \
  --no-make-circle-before-downwind \
  --no-make-270-before-downwind \
  --no-make-circle-middle-downwind \
  --no-make-circle-before-base \
  --no-make-270-before-base
```

```text
artifacts/traffic-patterns/
├── RJFM_RWY09_LEFT_MAKE_CIRCLES.kml
├── RJFM_RWY09_RIGHT_MAKE_CIRCLES.kml
├── RJFM_RWY27_RIGHT_MAKE_CIRCLES.kml
├── RJFM_RWY27_LEFT_MAKE_CIRCLES.kml
├── RJFM_ALL_MAKE_CIRCLE_PATTERNS.kml
├── RJFM_SHORT_DOWNWIND.kml
├── RJFM_SHORT_DOWNWIND_CIRCLE.kml
├── RJFM_SHORT_DOWNWIND_ENTRY_RWY27.kml
└── RJFM_SHORT_DOWNWIND_WITH_CIRCLE.kml
```

各通常場周KMLはCircle／270なしの本体を第1 Placemarkとし、ONにしたCircle／270を後続の独立Placemarkとして収録します。全場周の結合KMLでもこの分離を維持します。各座標へMSL高度[m]を保持し、`altitudeMode=absolute`、`extrude=1`を指定します。Google EarthではLineStyleを100%不透明・幅1.0、地面までの面を約10%不透明の同系淡色で塗り、PolyStyleのoutlineをOFFにします。既定はRWY 09がcyan、RWY 27がorangeで、個別KMLと結合KMLの両方に滑走路別styleを保持します。

Notebookのparameter cellではKMLの`AABBGGRR`順で次の4値を変更できます。Lineのalphaは`ff`（100%）、Fillのalphaは`1a`（約10%）を維持します。

```python
RWY09_LINE_COLOR = "ffffff00"
RWY09_FILL_COLOR = "1affffcc"
RWY27_LINE_COLOR = "ff00aaff"
RWY27_FILL_COLOR = "1a80d4ff"
```

CLIでは対応する`--rwy09-line-color`、`--rwy09-fill-color`、`--rwy27-line-color`、`--rwy27-fill-color`を指定します。他のTrajectory／ReferencePath KMLは明示的にstyleを渡さない限り従来どおりです。

## Short Downwind

`RJFM_SHORT_DOWNWIND.kml`はユーザー提示KMLの44座標、`RJFM_SHORT_DOWNWIND_ENTRY_RWY27.kml`は追加提示された水平1,000 ftの23座標を、longitude、latitude、absolute altitudeの順に変更せず保持します。これらはtask-provided geometryであり、公式手順や機体性能として扱いません。

単独のShort Downwind本体は両滑走路で共有するため共通styleを使用します。RWY27 EntryとCircle、および`RJFM_SHORT_DOWNWIND_WITH_CIRCLE.kml`内のEntry／Path／CircleはすべてRWY 27色です。

`RJFM_SHORT_DOWNWIND_CIRCLE.kml`は提示CircleのShort Downwind接点を保持し、RWY09 True Bearingに対する左法線上へ中心を置くことで接線関係を維持します。半径だけを110 KTAS・22° Bankの定常coordinated turnから求めた約808.22 mへ置き換え、1,000 ft MSLで時計回りに描画します。Roll遷移、wind、time-indexed dynamicsは含みません。

## Provenance

`宮崎空港及びその周辺における訓練飛行実施要領（R6.5.1改正）` p.1は北側通常・南側許容、場周高度1,000 ft（MSLとは明記しない）、滑走路末端通過後かつ700 ft以上での旋回開始を記載します。`学訓 第4章 改正19` p.2図は場周高度を1,000 ft AGLとして図示し、p.1-2はTPAの300 ft手前からのCrosswind、上昇中20°、Level Off後/Downwind/Base 30°、Final標準25°（最大30°）、Downwind 1.5 NMと宮崎の1.2 NM騒音軽減指定を記載します。RWY27の指定地点通過後旋回も含め、これらはこのReferencePathでは再現しません。

このモデルはtask指定に従って場周高度を1,000 ft MSLとして適用し、ユーザー選択により、1.2 NMを相反するCrosswind/Baseの共通axisとして扱い、Aiming MarkerからUpwind turn開始までに比例上昇します。110 KTAS、各Bank、10°/s Roll、3° Final、Aiming Marker規則、Before Downwind/BaseのMake Circle/Make 270有無はtask-provided入力です。旋回半径とRoll積分は`physics_derived`、組み立てたpath全体とShort Downwind Circleの配置は`assumption_dependent`です。Reference Data tableやwindをこの幾何の根拠として使用しません。

## 数値回帰とsource整合確認

PR #7を含むmain基準（`97a8ec5`）から、RJFMの4方向×32 Boolean設定について単一経路・全独立componentとShort Downwindを数値snapshot化しています。テストは追加したAbeam vertexを除いた全既存座標・MSL高度を比較します（緯度経度10桁、高度6桁へ丸めたdigest）。Abeamが従来のDownwind直線上にあることは別の数値テストで検証します。

既存の球面近似による閾値方位との0.1°整合許容差は、canonical RJFC/RJFG/RJFK/RJFUの約0.11–0.13°、RJFOの約0.422°差を拒否していました。8空港を読み込むため、source sanity checkの許容差を0.5°としました。これはデータ補正ではありません。AIP True Bearing、両threshold、center pointは保持し、既存の中心・True Bearing・測定滑走路長から構成する幾何も維持します。公開方位と座標の差があるため、構成上のlanding-threshold pointはAIP閾値座標そのものと完全一致する保証はありません。長さ整合許容差15 mは従来どおりです。

## RJF* 7空港の共通builder（Issue #9）

`data.airports.traffic_profiles.rjf_traffic_pattern_specs(icao)`は、canonical
JSONを共通loaderで読み込み、以下の運用表から4本の`TrafficPatternSpec`を返します。
`examples.rjf_traffic_patterns.build_rjf_traffic_patterns(icao, **switches)`は、
各specと通常場周・選択した独立componentの組を返します。既存geometry engineを
共有し、空港ごとのgeneratorやNotebookは追加しません。

| ICAO | RWY × side | 高度 ft MSL | 降下開始 | Preferred | 高度根拠 |
| --- | --- | ---: | --- | --- | --- |
| RJFS | 11 LEFT / 29 RIGHT | 1000 | Base Turn start | no | local explicit |
| RJFS | 11 RIGHT / 29 LEFT | 1000 | Base Turn start | yes（南） | local explicit |
| RJFO | 01 LEFT / 19 RIGHT | 1300 | Abeam Threshold | no | local explicit（西） |
| RJFO | 01 RIGHT / 19 LEFT | 1000 | Base Turn start | yes（東・海） | generic: 17 + 1000 → 1000 |
| RJFK | 16・34 × LEFT/RIGHT | 1900 | Base Turn start | no | generic: 891 + 1000 → 1900 |
| RJFT | 07 LEFT / 25 RIGHT | 1400 | Base Turn end | no | local explicit（北） |
| RJFT | 07 RIGHT / 25 LEFT | 1700 | Base Turn start | no | local explicit（南override） |
| RJFG | 13 LEFT / 31 RIGHT | 1800 | Base Turn start | yes（北） | local explicit |
| RJFG | 13 RIGHT / 31 LEFT | 1800 | Base Turn start | no | local explicit |
| RJFU | 14・32 × LEFT/RIGHT | 1000 | Base Turn start | no | generic: 8 + 1000 → 1000 |
| RJFC | 14・32 × LEFT/RIGHT | 1100 | Base Turn start | no | generic: 122 + 1000 → 1100 |

7空港ともDownwind offsetとCrosswind/Base extensionは1.5 NM / 1.5 NMです。
RJFMの1.5 / 1.2 NMは変更しません。共通値は110 KTAS、Upwind→Crosswind
30°、ordinary Downwind/BaseとCircle/270 22°、Final turn 25°、Roll 10°/s、
Final glide 3°です。Preferredはmetadataであり、常に両滑走路×両側を生成します。

情報基準時点は[Source snapshotの定義](data-sources.md#information-baseline)を参照してください。

運用値の直接の転記元は[Issue #9](https://github.com/Yuto-24/sr22-course-simulator/issues/9)
で提供された航大資料の記述です。佐賀は
`航空大学校所属航空機の他空港利用に関する調整事項[2026.4.1].pdf`、
他のlocal値・注意事項は`学生訓練実施要領 改正19`の空港情報に基づきます。
元の運用PDFを今回あらためて転記・照合したものではなく、不明なページを補いません。
熊本北側1400 ftはIssueにあるAIP AD2.23のsingle-engine nominalとも整合し、
南側1700 ftは航大local運用の明示overrideとして記録します。

Generic ruleは同要領第4章通常DepartureのAGL+1000 ftと、第3章Approach
briefingの釧路311 ft→1300 ft例を根拠とするIssue指定の丸めです。
`floor((field_elevation_ft + 1000 + 50) / 100) * 100`を適用し、50 ft境界で
banker's roundingを使いません。標高は実行時にcanonical airport JSONから取得します。
`spec.notes`と`spec.source.notes`で`local_explicit` / `generic_field_plus_1000`を
区別します。種子島1800 ftはlocal記述の明示値として保持します。

大分西側の810 ft terrain、鹿児島のterrain/traffic、長崎のentry注意事項は
metadataとして保持し、形状の除外・変形やterrain clearanceの保証にしません。
屋久島のIFR Circling EAST onlyをVFR側の制約に流用しません。長崎の海上飛行という
事情だけからpreferredを推定しません。未登録空港には、足りない運用profileの
高度・降下・preferred根拠を明記したmodel-gapエラーを返します。

このReferencePathの高度は既存の区間補間を使い、指定降下開始点から3° Finalへ
連続接続します。Abeamから接地まで全区間を厳密な3°とするflight guidanceでは
ありません。CircleはTPAでの独立比較経路です。Before Base 270の降下・合流の
扱いも上記共通仕様を使います。風・動力学・地形回避の追加モデルはありません。

### 共通CLI / KML

```bash
# 全7空港: 個別28 + 空港別combined 7 = 35ファイル
PYTHONPATH=src python3 -m sr22_course_simulator.examples.rjf_traffic_patterns \
  --output-dir artifacts/rjf-traffic-patterns

# installed entry point、空港指定、各Booleanを独立に指定
sr22-rjf-patterns --airport RJFO --make-circle-before-base --no-make-270-before-base
```

5個の`--make-*` / `--no-make-*`はRJFM CLIと同じ名称と初期値を使います。
Before Base Circleのみ既定OFF、他4個はONです。全OFFなら通常場周のみを生成します。
各空港は`ICAO_RWYxx_LEFT_TRAFFIC_PATTERN.kml`、
`ICAO_RWYxx_RIGHT_TRAFFIC_PATTERN.kml`を両滑走路分と、
`ICAO_ALL_TRAFFIC_PATTERNS.kml`を出力します。Placemark名も同じcanonical identity
で始まり、通常本体と各Circle/270を分離します。KML座標はlongitude・latitude・
MSL altitude[m]順、`altitudeMode=absolute`です。各Placemarkのdescriptionには
JSONでpreferred、高度、降下開始、注意事項、運用出典、canonical airport/runway
の全`SourceCitation`（effective date・section・source hashを含むnotes）を保持します。

`tests/test_rjf_traffic_patterns.py`は28場周×32設定、相反滑走路のphysical side、
1.5 NMの各axis、Abeam、降下開始と3° Final、35 KMLの全座標とmetadataを検証します。
既存RJFMの座標snapshot・Short Downwind・CLIテストも継続します。
