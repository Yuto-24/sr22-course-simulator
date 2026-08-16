# Notebook Workflow

## 目的

`notebooks/spiral_descent_walkthrough.ipynb` は、Spiral Descent の構成要素を一度に隠して実行せず、次の順序で確認するためのチュートリアルです。

1. 学生訓練実施要領の本文から転記した `ManeuverSpec` を確認する。
2. `InitialState`、`Environment`、明示的な model assumption を入力する。
3. 風に依存しない `ReferencePath` を生成する。
4. Guidance と Aircraft Model を組み立てる。
5. 風の影響を受ける `Trajectory` を計算する。
6. 終了理由、根拠ラベル、グラフを確認する。
7. CSV / KML / PNG を保存する。

`notebooks/miyazaki_traffic_patterns.ipynb` は別の workflow です。RJFM の Airport / Runway master data、threshold 中点の RWY Center Point、True Bearing、4本の風に依存しない Normal Traffic Pattern を順に確認し、`artifacts/traffic-patterns/` へ KML を保存します。ARP は表示・sanity check 専用です。

現在の Spiral Descent 出力は、POH で検証された降下性能ではありません。確認済み POH Chapter 5 には 110 kt / 約 10% PWR / Bank 45〜55° の領域を定義する降下性能表がないため、Notebook でも `AssumedSteadyPointProvider` と固定迎角 closure を使用し、結果に `assumed` を残します。

## Docker で起動する

### Linux

Repository root で実行します。

```bash
mkdir -p artifacts
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up --build notebook
```

`LOCAL_UID` / `LOCAL_GID` を container user に反映するため、Notebook と生成物をホスト側ユーザーで編集できます。

### Windows / macOS

Docker Desktop では UID / GID を指定せずに起動できます。

```bash
docker compose up --build notebook
```

起動ログに次の形式の URL が表示されます。

```text
http://127.0.0.1:8888/lab?token=...
```

URL を開き、`spiral_descent_walkthrough.ipynb` を選択します。終了時は起動した Terminal で `Ctrl+C` を押します。

場周経路を生成する場合は、同じ JupyterLab で `miyazaki_traffic_patterns.ipynb` を選択して上から実行します。

Notebook は `127.0.0.1` にだけ公開します。Token 認証を無効化していません。

## 条件を変えて実行する

Notebook の `### 2. 初期状態・風・明示的な仮定を入力する` が主な編集箇所です。

- `InitialState`: 緯度、経度、高度、True Heading、TAS、機体質量、payload、燃料
- `Environment`: 気象風向 FROM、風速、地表標高 MSL
- explicit assumptions: airspeed kind の解釈、Reference Path の降下量、trim、controller gain
- numerical settings: Path 点数、時間刻み、最大 step 数

値を変えた後は、その parameter cell から下を順番に実行するか、JupyterLab の `Run > Run All Cells` を使います。上のセルに依存するため、途中のセルだけを順不同で実行しないでください。

学訓本文から得た次の意味は parameter cell に複製しません。

- Target
- Limit
- Nominal
- Initial Setting
- Control Relationship
- termination condition

これらは `ManeuverSpec` から取得します。章末 Reference Data は Notebook 冒頭で比較用に表示しますが、Guidance や Aircraft Model の入力には使用しません。

## 保存されるもの

Docker container 内の `/workspace/notebooks` はホストの `notebooks/`、`/output` はホストの `artifacts/` に bind mount しています。

| ホスト側の場所 | 内容 | Git 管理 |
| --- | --- | --- |
| `notebooks/spiral_descent_walkthrough.ipynb` | 入力セル、説明、保存したセル出力 | 対象 |
| `notebooks/miyazaki_traffic_patterns.ipynb` | RJFM master data、4 pattern、KML 出力 | 対象 |
| `artifacts/guided-trajectory.csv` | 1 state 1 row の時系列、単位付き列、evidence | 対象外 |
| `artifacts/guided-trajectory.kml` | 風の影響を受けた Trajectory | 対象外 |
| `artifacts/guided-reference-path.kml` | 風と独立した Reference Path | 対象外 |
| `artifacts/guided-ground-track.png` | Trajectory と Reference Path の平面比較 | 対象外 |
| `artifacts/guided-altitude-time.png` | 高度 MSL の時系列 | 対象外 |
| `artifacts/guided-trajectory-3d.png` | 3 次元比較 | 対象外 |
| `artifacts/traffic-patterns/*.kml` | RJFM の個別4 path と結合 KML | 対象外 |

Notebook のセル出力を `.ipynb` に残す場合は、JupyterLab の `File > Save Notebook` を実行します。CSV / KML / PNG は各セルの実行時に上書きされます。

CSV の aviation-facing 列と SI 列は列名で区別します。例: `altitude_m` / `altitude_ft`、`true_airspeed_mps` / `true_airspeed_kt`、`vertical_speed_mps` / `vertical_speed_fpm`。内部計算は SI 単位です。

## Source code を変更した場合

Notebook ファイルは bind mount しているため、セルの編集は直ちに反映されます。`src/` は image build 時に copy するため、Python source や canonical data を変更した場合は image を作り直します。

```bash
docker compose build notebook
docker compose up notebook
```

## ローカル Python で起動する

Python 3.11 以上を用意し、repository root で実行します。

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

Notebook の既定出力先は repository の `artifacts/` です。`SR22_ARTIFACT_DIR` を設定した場合はその path を使用します。

## Notebook を自動検証する

Notebook を top-to-bottom で実行し、source Notebook を変更せず実行済み copy を `/tmp` に作る例です。

```bash
docker compose run --rm notebook \
  python -m jupyter nbconvert \
  --execute \
  --to notebook \
  --output /tmp/spiral-descent-executed.ipynb \
  --ExecutePreprocessor.timeout=180 \
  spiral_descent_walkthrough.ipynb
```

全回帰テストは別の軽量 image で実行します。

```bash
docker compose run --rm test
```

## よくある問題

### 8888 port が使用中

別の localhost port を指定します。

Linux / macOS:

```bash
JUPYTER_PORT=8890 docker compose up notebook
```

Windows PowerShell:

```powershell
$env:JUPYTER_PORT = "8890"
docker compose up notebook
Remove-Item Env:JUPYTER_PORT
```

この場合、URL は `http://127.0.0.1:8890/lab?token=...` です。

### Token 付き URL が分からない

起動中の service log を表示します。

```bash
docker compose logs notebook
```

### `artifacts/` に書き込めない

Linux では最初の image build から UID / GID を指定します。

```bash
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose build notebook
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up notebook
```

異なる UID / GID で作った既存 image が使われる場合は、同じ環境変数を付けて `docker compose build --no-cache notebook` を一度実行します。
