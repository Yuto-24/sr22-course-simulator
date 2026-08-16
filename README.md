# sr22-course-simulator

Cirrus SR22 を対象に、航空大学校の訓練で扱う飛行経路・飛行入力・風・機体性能を結び付け、3 次元軌跡と必要な飛行入力を計算・可視化するためのシミュレータです。

このプロジェクトは、完全な 6-DoF Flight Dynamics Simulator を再現することを主目的にしません。訓練で直接扱う `Pitch`、`Bank`、`PWR`、`Flap`、学生訓練実施要領の本文に規定された課目の目的・諸元・修正要領、SR22 飛行規程第 5 章の性能データを組み合わせる **performance-based / quasi-steady simulator** を目指します。

## まず Notebook で動かす

Docker が使える Linux では、repository root で次を実行します。

```bash
mkdir -p artifacts
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up --build notebook
```

Windows / macOS の Docker Desktop では `LOCAL_UID` / `LOCAL_GID` を省略します。

```bash
docker compose up --build notebook
```

Terminal に表示された `http://127.0.0.1:8888/lab?token=...` をブラウザで開き、`spiral_descent_walkthrough.ipynb` を選びます。Notebook の `### 2. 初期状態・風・明示的な仮定を入力する` で条件を編集し、上から順に実行してください。

宮崎空港の4本の場周経路を確認する場合は `miyazaki_traffic_patterns.ipynb` を選びます。ARP は参照用に保持し、RWY09 / RWY27 の threshold 中点を RWY Center Point として True Bearing で経路を生成します。詳しい定義は [Airport Traffic-Pattern Reference Paths](docs/traffic-patterns.md) を参照してください。

結果は repository の `artifacts/` に保存されます。

```text
artifacts/
├─ guided-trajectory.csv       各時刻の状態量と根拠ラベル
├─ guided-trajectory.kml       風の影響を受けた実軌跡
├─ guided-reference-path.kml   風と独立した基準経路
├─ guided-ground-track.png     平面経路
├─ guided-altitude-time.png    高度の時系列
└─ guided-trajectory-3d.png    3 次元表示
```

Notebook の編集内容は `notebooks/spiral_descent_walkthrough.ipynb` に保存されます。生成物を入れる `artifacts/` は Git 管理対象外です。詳しい手順とトラブルシューティングは [Notebook Workflow](docs/notebook-workflow.md) を参照してください。

## どこを編集・確認するか

| 目的 | 場所 | 保存先 / 反映方法 |
| --- | --- | --- |
| 初期状態、風、明示的な仮定を変えて試す | `notebooks/spiral_descent_walkthrough.ipynb` の parameter cell | Notebook の表示と `artifacts/` |
| 課目本文由来の意味を確認・修正する | `src/sr22_course_simulator/maneuver/` | test 後に image を再 build |
| 機体応答・積分処理を変更する | `src/sr22_course_simulator/aircraft/`、`simulation/`、`guidance/` | test 後に image を再 build |
| POH の canonical data を追加する | `src/sr22_course_simulator/data/poh/canonical/` | node 再現・範囲外拒否 test を追加 |
| 数値の時系列を確認する | `artifacts/guided-trajectory.csv` | 単位は列名に明記 |
| 3D 経路を確認する | `artifacts/*.kml` | Reference Path と Trajectory は別ファイル |
| RJFM 場周経路を生成する | `notebooks/miyazaki_traffic_patterns.ipynb` | `artifacts/traffic-patterns/*.kml` |

## 目的

主に次を扱います。

- 環境と飛行入力から航空機の 3 次元軌跡を計算する。
- 各課目・各空港の基準経路を純粋な幾何学として生成し、KML 等へ出力する。
- 基準経路と環境から、その経路・諸元を維持するために必要な `Pitch` / `Bank` / `PWR` / `Flap` を計算・可視化する。
- 無風時と風あり時で各訓練課目の軌跡を比較する。
- NAV の変針、風力三角形、Cut Angle、Intercept、飛行時間を計算する。
- 将来的に MSM 予想風や実飛行データと接続する。

## 重要な設計原則

### 学訓 Reference Data はモデルの基準ではない

航空大学校「学生訓練実施要領 単発事業用課程」本文は、Power Setting と Pitch Attitude を「所望の諸元を得るためのおおよその目安」と位置付け、重量・外部環境によって変化するとしています。

第 4 章・第 5 章末尾の `Reference Data` についても、Pitch / Power は概ね標準大気での値で、重量・気温・高度等によって変化し、Reference に合わせようとして計器に集中しないよう注意されています。

したがって本プロジェクトでは、**課目そのものは学訓本文から定義**します。

```text
学訓本文
├─ 課目の目的
├─ 手順 / Phase
├─ 維持すべき諸元
├─ 修正に用いる入力
├─ 経路・地上目標との関係
├─ Limit / 最低高度
└─ 終了条件
```

章末 `Reference Data` は次の用途に限定します。

- solver の初期推定値
- UI 上の参考値
- 計算結果との比較
- sanity check
- 原資料の追跡

Reference Data の行だけから課目や機体モデルを構築してはいけません。

## ソースの役割

単純な「優先順位」ではなく、資料ごとに役割を分けます。

### 学生訓練実施要領 本文

**訓練課目の定義・操作思想・目標・修正要領・安全条件**の根拠です。

例えば Basic Flight 本文は、基本的に高度修正を Pitch、速度修正を Power で行うことを明示しています。こうした「何を何で Control するか」をモデルへ直接反映します。

### SR22 型式証明飛行規程 / POH

**航空機の性能・限界・性能表**の根拠です。

第 5 章 Performance Data を機械可読化し、資料が持つ軸の範囲内で多次元補間を行い、Aircraft / Performance Model の主要な定量データとして使用します。

### 解析的な物理・幾何

POH と学訓を接続するため、根拠が明確な関係を使用します。

例:

- coordinated turn の旋回率・旋回半径
- wind vector と air / ground velocity の合成
- 座標・経路幾何
- fuel burn と weight propagation

### 学訓 Reference Data

**参考値のみ**です。本文に規定された諸元・操作関係を上書きしません。

## 2 つの主要 Workflow

### Forward Simulation

操縦者側から飛行入力を直接与え、その結果を求めます。

```text
Initial Aircraft State
        +
Environment
        +
Flight Input
        |
        v
Aircraft / Performance Model
        |
        v
Trajectory
```

基本 Flight Input:

- Pitch
- Bank
- PWR
- Flap

Heading は通常の連続入力ではなく状態量です。`Initial Heading` は Initial State、`Target Heading` や `Target Altitude` は必要に応じて Goal / Termination Condition として扱います。

### Procedure / Path-driven Guidance

課目本文または Reference Path が要求する経路・諸元を、現在の環境下で維持するための入力を求めます。

```text
ManeuverSpec / ReferencePath
          +
Environment
          +
AircraftModel
          |
          v
Guidance Solver
          |
          v
Pitch / Bank / PWR / Flap
          |
          v
Forward Simulation
          |
          v
Simulated Trajectory
```

Reference Path は「本来維持したい地上経路」で、風によって移動させません。風によって変わるのは、その Path を維持するための機首方位・Bank・その他の入力と実軌跡です。

## Aircraft State と Environment

### Initial State

少なくとも次を持ちます。

- Position
- Altitude
- Heading
- Airspeed
- Initial loading / non-fuel weight
- Initial fuel

### Dynamic Aircraft State

飛行中に更新します。

- Position / Altitude
- Heading / Track
- Airspeed / GS / VS
- Pitch / Bank / PWR / Flap
- Fuel remaining / fuel burned
- Current weight

Weight は Environment ではありません。初期搭載状態と燃料から初期重量を求め、燃料消費に応じて飛行中の Weight を変化させます。

### Environment

- Wind
- Temperature
- Pressure / Pressure Altitude
- 将来: 位置・高度・時刻依存の気象場

## 現在の機体構成前提

- 対象は SR22。
- 固定脚として扱い、Gear を可変状態・入力にしない。
- 航空大学校での対象機構成として Nose Wheel Pant / Fairing は常時取り外し状態を前提とする。
- 通常課目では coordinated flight を仮定する。
- Rudder / sideslip は通常入力にしない。
- Forward Slip 等の意図的 sideslip は将来拡張とする。

## POH 多次元補間

POH 第 5 章の補間は Aircraft Model の中心技術です。

- 元表を canonical data として保存する。
- 元表の node は正確に再現する。
- 高度・温度 / ISA deviation・PWR・Weight・Configuration 等、**実際に資料が持つ軸のみ**を使用する。
- 原則として外挿しない。
- 補間値と元表値を区別する。
- 複数の表を結合する場合は、成立条件・定義・単位が整合することを確認する。

POH の補間から得られる性能値と、学訓本文の Target / Control Relationship、旋回・風等の解析式を組み合わせて軌跡を解きます。

任意の `Pitch × Bank × PWR × Flap` に対して資料が十分でない場合、滑らかな数値を捏造せず、その operating region を unsupported / assumption-required として扱います。

## ドキュメント

- [Architecture](docs/architecture.md)
- [Modeling Policy](docs/modeling.md)
- [Maneuver Specification](docs/maneuver-specification.md)
- [Data Sources and Interpolation](docs/data-sources.md)
- [Validation](docs/validation.md)
- [Notebook Workflow](docs/notebook-workflow.md)
- [Airport Traffic-Pattern Reference Paths](docs/traffic-patterns.md)
- [Roadmap](docs/roadmap.md)
- [Agent Rules](AGENTS.md)

## 現在の実装

初回の共通基盤と Spiral Descent 最小実用版を Python package として実装済みです。

- SI 単位、地理座標、`InitialState` / `AircraftState` / `Trajectory`
- `FlightInput = Pitch / Bank / PWR / Flap`（Gear / Rudder なし）
- `NoWind` / `ConstantWind`、気象風向 FROM convention、交換可能な Wind Provider
- mass-based loading、fuel burn、飛行中の weight propagation
- narrative の Target / Limit / Nominal / Initial Setting / Control Relationship / Path / Phase / Termination と Advisory Reference の型分離
- canonical POH table、strict JSON loader、N 次元 multilinear interpolation、source-domain 外拒否、provenance / applicability metadata
- direct-input Forward Simulation と、別 API の Spiral Descent Guidance Simulation
- wind-independent `ReferencePath` と time-indexed `Trajectory`
- 2D Ground Track、Altitude-Time、3D plot helper（Matplotlib は optional）
- Trajectory の CSV export、Trajectory / Reference Path の KML 3D LineString export
- AIP 転記値を保持する `AirportSpec` / `RunwaySpec`、ARP 非依存の RWY Center Point、RJFM の4本の Normal Traffic Pattern と multi-Placemark KML

### Source coverage

原資料を確認し、次を実装へ反映しています。

- 学生訓練実施要領 改正19、Chapter 5 Spiral Descent 本文 5-(34)〜5-(35)：110 kt、Entry 約 10% PWR、Pitch による速度 Control、Bank 45° / 最大 55°、Pylon / Drift correction、720°、Recovery
- 同 5-(1)：最低訓練高 AGL 2,000 ft
- 同 5-(49)：Reference Data row を `AdvisoryReference` としてのみ保持
- SR22 G6 型式証明飛行規程 P/N 13772-006J、Chapter 5 p.5-32：2,000 ft / 2500 RPM cruise slice の canonical source nodes

PDF 自体は repository に含めません。

重要な model gap として、確認した POH Chapter 5 には 110 kt / 約 10% PWR / Bank 45〜55° の Spiral Descent を定義する descent performance table がありません。したがって package はこの領域を source-backed SR22 performance として扱いません。実行例は caller-supplied の `AssumedSteadyPointProvider` と固定迎角 closure を使用し、すべて `assumed` として明示します。

## ローカルで Notebook を使う

Linux / macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[notebook]'
.venv/bin/python -m jupyter lab --ServerApp.root_dir=notebooks
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[notebook]"
.\.venv\Scripts\python.exe -m jupyter lab --ServerApp.root_dir=notebooks
```

表示された URL を開きます。Notebook の既定出力先は repository の `artifacts/` です。

## Test

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
```

Docker の test target で実行する場合:

```bash
docker compose run --rm test
```

## 1 回だけ CLI で実行する

Guidance demo を実行し、KML を `artifacts/guided-spiral.kml` に保存します。

Linux / macOS:

```bash
mkdir -p artifacts
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose run --rm simulator
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force artifacts | Out-Null
docker compose run --rm simulator
```

ローカル install 後は同じ demo を直接実行できます。出力は assumption-dependent であり、POH-validated descent prediction ではありません。

```bash
sr22-spiral-demo --mode guided --kml artifacts/guided-spiral.kml
```

Direct-input experiment:

```bash
sr22-spiral-demo --mode forward --calm --kml artifacts/forward-spiral.kml
```

Python API では `simulate_forward(...)` は ManeuverSpec を受け取らず、`simulate_guided_spiral_descent(...)` は narrative-derived `ManeuverSpec` と別オブジェクトの `PylonSpiralPath` を受け取ります。この分離により、固定入力実験を公式課目の再現として誤表示しません。

`PYTHON_VERSION`、`LOCAL_UID`、`LOCAL_GID`、`JUPYTER_PORT` は Compose の環境変数として上書き可能です。`PYTHON_VERSION` が解決する interpreter は Python 3.11 以上でなければならず、それ未満では image build が明示的に失敗します。Container は非 root user で動作し、PDF 原資料を image に含めません。Matplotlib / Jupyter は notebook image にだけ含め、CLI runtime image には含めません。
