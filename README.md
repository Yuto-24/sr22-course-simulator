# sr22-course-simulator

Cirrus SR22 を対象に、航空大学校の訓練で使用する飛行諸元・経路・風をもとに、軌跡と必要な飛行入力を計算・可視化するためのシミュレータです。

このリポジトリは、実機の 6-DoF Flight Dynamics Simulator を再現することを主目的にしません。訓練で実際に意識する `Pitch`、`Bank`、`PWR`、`Flap` と、SR22 の性能資料・訓練 Reference Data を結び付け、飛行経路・地上軌跡・NAV 計算を扱える実用的な performance-based simulator を目指します。

## 目的

主に次の問題を扱います。

- 環境と飛行入力から、航空機の 3 次元軌跡を計算する。
- 基準経路そのものを生成し、KML 等へ出力する。
- 基準経路と環境から、その経路を維持するために必要な `Pitch` / `Bank` / `PWR` / `Flap` を求める。
- 無風時と風あり時で、各訓練課目の軌跡を比較する。
- NAV の変針、風力三角形、Cut Angle、Intercept、飛行時間を計算する。
- 将来的に予想風データや実飛行データと接続する。

## 中心となる設計

### Forward Simulation

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

Flight Input の基本要素は次のとおりです。

- Pitch
- Bank
- PWR
- Flap

Heading は基本的な入力ではなく状態量です。`Initial Heading` は初期状態として必要です。必要に応じて `Target Heading` や `Target Altitude` を Segment の終了条件・目標として使用します。

### Reference Path / Guidance

```text
Reference Path ------------------------> KML / geometry output
      |
      + Environment
      + Aircraft Model
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

Reference Path は風に依存しない「本来維持したい地上経路」として定義します。その経路を特定の環境下で維持するために必要な入力は Guidance 側で計算します。

## 現在の主要なモデル前提

- SR22 は固定脚のため、Gear 状態はシミュレーション入力・状態として持ちません。
- 航空大学校機の前輪カバー運用を反映し、nose wheel pant / fairing は常時取り外し状態を基準構成とします。
- 通常の課目では coordinated flight を仮定し、Rudder / sideslip を明示的な入力として扱いません。
- Forward Slip 等、意図的な sideslip を必要とする課目は将来拡張とします。
- Weight は Environment ではなく aircraft state です。初期重量と燃料を起点に、燃料消費に応じて飛行中の重量を更新します。
- 内部計算は SI 単位を原則とし、操縦・表示・資料との入出力では ft / kt / NM / fpm / deg / %PWR 等を使用します。

## Reference Data

モデルの主要な根拠は次の資料を想定しています。

1. 航空大学校「学生訓練実施要領 単発事業用課程」
   - 第4章 4-18 `Reference Data`
   - 第5章 5-12 `Reference Data`
2. SR22 G6 型式証明飛行規程 / POH
   - 第5章 `Performance Data`

学訓の Reference Data は課目ごとの nominal operating point、飛行規程第5章は高度・温度・出力等に対する性能データとして扱います。両者を混同せず、出典・適用条件を保持したままモデル化します。

## ドキュメント

- [Architecture](docs/architecture.md)
- [Modeling Policy](docs/modeling.md)
- [Data Sources and Interpolation](docs/data-sources.md)
- [Validation](docs/validation.md)
- [Roadmap](docs/roadmap.md)
- [Agent Rules](AGENTS.md)

## Status

現在は設計フェーズです。最初の実用機能として Spiral Descent の 3D trajectory、性能データ補間、KML 出力を優先して実装します。
