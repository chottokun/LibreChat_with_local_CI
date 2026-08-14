---
type: Concept
title: Caddy SSL & Artifacts Integration
description: Caddyリバースプロキシ設定、Sandpack Bundler (Artifacts) のDocker Compose Profilesによる段階的導入運用
status: active
timestamp: 2026-08-14T09:30:00+09:00
tags:
  - infrastructure
  - caddy
  - ssl
  - artifacts
  - sandpack
---

# Caddy SSL & Artifacts Integration (Caddy SSL と Artifacts 連携)

## 1. 概要

LibreChat の Artifacts 機能（React 等の UI をリアルタイムレンダリングする Sandpack Bundler）は、ブラウザのセキュリティ制限（クロスオリジン通信・Mixed Content 制限）により、HTTPS（SSL/TLS）環境での稼働が前提となります。

本プロジェクトでは、単一ブランチ（メインブランチ）を維持しながら、非SSL環境とSSL本番環境をシームレスに切り替えるため、Docker Compose の **Profiles（プロファイル）機能** を活用した段階的導入設計を採用しています。

## 2. 段階的導入ロードマップ

```mermaid
graph TD
    A[メインブランチ: 単一コードベース] --> B(フェーズ1: 非SSL環境 / 現在)
    A --> C(フェーズ2: ローカルSSL検証 / 移行期)
    A --> D(フェーズ3: 社内CA本番 / オンプレ本番)

    subgraph "起動プロファイルによる制御"
        B -->|profiles指定なし (通常起動)| P1["LibreChat + RCE のみ起動<br>(Bundlerコンテナ完全休止)"]
        C -->|--profile ssl-mode| P2["Caddy + Bundler + LibreChat + RCE 起動"]
        D -->|--profile ssl-mode| P3["正規SSL証明書適用フルスタック起動"]
    end
```

* **フェーズ1（非SSL環境）**:
  HTTP環境での運用。Sandpack Bundlerを休止させ、余計なリソースを消費せずにチャットおよびRCE（データ分析）を実行。
* **フェーズ2（SSL検証環境）**:
  Caddyによる自己署名証明書またはプライベートCA証明書を適用し、Artifactsレンダリングを検証。
* **フェーズ3（オンプレミス本番）**:
  組織内プライベートCAが発行した証明書を配布し、セキュアにフル機能（Artifacts）を運用。

## 3. Docker Compose Profiles 設定

`docker-compose.librechat.yml` で `sandpack-bundler` にプロファイルを設定しています。

```yaml
sandpack-bundler:
  image: ghcr.io/librechat-ai/codesandbox-client/bundler:latest
  container_name: sandpack-bundler
  restart: always
  ports:
    - "8080:80"
  profiles:
    - ssl-mode  # --profile ssl-mode 指定時のみ起動
  networks:
    - librechat-network
```

### 起動コマンド
* **通常起動（非SSL）**:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
  ```
* **SSL & Artifacts 有効化起動**:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.librechat.yml --profile ssl-mode up -d
  ```

## 4. 関連ドキュメント
* [Docker Setup & Storage Modes](./docker-setup.md) - Docker起動手順
* [Configuration Reference](./configuration.md) - 環境変数設定
