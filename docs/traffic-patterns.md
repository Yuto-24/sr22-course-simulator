# Airport Traffic Pattern and Independent Turn Reference Paths

## 対象とモデル境界

宮崎空港 RJFM の4本の Traffic Pattern を生成します。

- RWY09 NORTH / SOUTH
- RWY27 NORTH / SOUTH

各RWY／NORTH・SOUTHについて、Aiming Markerから同じAiming Markerへ戻る通常場周本体と、選択したCircle／270を別々の`PolylineReferencePath`として生成します。通常場周本体へCircleや270を連結しないため、KMLでは各Placemarkを独立して表示できます。110 KTAS、Bank、Roll rateは曲線形状を構築する入力であり、出力はwindやtime-indexed aircraft dynamicsを含む`Trajectory`ではありません。

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

## 高度

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
├── RJFM_RWY09_NORTH_MAKE_CIRCLES.kml
├── RJFM_RWY09_SOUTH_MAKE_CIRCLES.kml
├── RJFM_RWY27_NORTH_MAKE_CIRCLES.kml
├── RJFM_RWY27_SOUTH_MAKE_CIRCLES.kml
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
