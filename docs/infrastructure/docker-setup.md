---
type: Concept
title: Docker Setup & Storage Modes
description: Docker Compose 構成、フルスタック/単体起動手順、ストレージモード (put_archive vs Volume Mount)
status: stable
generated:
  by: agent/gemini-3.7-flash
  at: 2026-08-14T09:30:00+09:00
tags:
  - infrastructure
  - docker-compose
  - storage
---

# Docker Setup & Storage Modes (Docker構成とストレージモード)

## 1. 概要

本プロジェクトは Docker Compose をベースに構築されており、API単体起動および LibreChat や MongoDB、Meilisearch を含めたフルスタック起動の2通りの構成をサポートしています。また、実行環境のファイル転送方式として2種類のストレージモードを備えています。

## 2. 起動構成とコマンド

### A. フルスタック構成 (LibreChat + API + DB + Nginx)
1. **設定ファイルの準備**:
   ```bash
   cp .env.librechat .env
   # JWT_SECRET, CREDS_KEY, LIBRECHAT_CODE_API_KEY を設定
   ```
2. **サンドボックスイメージのビルド**:
   ```bash
   docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
   ```
3. **起動 (SSL/TLS リバースプロキシ推奨)**:
   Nginx リバースプロキシ経由で HTTPS (443) および Sandpack Bundler (8443) を有効化して起動します（`./certs` 配下に証明書が必要）：
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.librechat.yml --profile ssl-mode up -d
   ```
   * **Web UI (HTTPS)**: `https://<サーバーのIPまたはホスト名>` (または `https://localhost`)
   * **HTTPアクセス**: ポート 80 宛ての通信は自動的に HTTPS (443) に 301 リダイレクトされます。

   <details>
   <summary>SSLプロファイルを使わない最小構成（ローカルHTTP）で起動する場合</summary>

   Nginx を介さず、LibreChat 本体のみを直接起動します：
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
   ```
   * **Web UI (HTTP)**: `http://localhost:3000` (または `http://127.0.0.1:3000`)
   * **注意**: セキュリティ保護のため、LibreChat 本体のポートはホストマシンのループバック (`127.0.0.1:3000`) にのみバインドされています。外部の別PCやスマホ等のブラウザからアクセスする場合は、上記 **SSL/TLS モード (`--profile ssl-mode`)** を使用してください。
   </details>

### B. API単体構成 (既存LibreChatとの連携)
```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
docker compose up -d --build
```

### C. GPU対応構成 (オプション)
```bash
docker build -f Dockerfile.rce.gpu -t custom-rce-kernel-gpu:latest .
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## 3. ストレージモードの比較と選定

| 項目 | 標準モード (`put_archive`) | ボリュームマウントモード |
|---|---|---|
| **設定方法** | `RCE_DATA_DIR` を未設定（デフォルト） | `RCE_DATA_DIR` にホストの絶対パスを指定 |
| **ファイル転送方式** | Docker API (`put_archive` / `get_archive`) | ホスト共有ディレクトリの直接読み書き |
| **パフォーマンス** | 中（tarストリーム化のオーバーヘッドあり） | **極めて高速** |
| **権限要件** | 特別なホストパーミッション不要 | ホスト側ディレクトリに **UID 1000** の書込権限が必要 |
| **用途** | 開発環境、パーミッション設定が困難な環境 | 大容量データを扱う本番・高速化環境 |

### ボリュームマウント時の権限設定とセッション隔離
* **権限設定**: ボリュームマウントモードを使用する場合は、ホスト側ディレクトリの所有者を `sandboxuser` (UID 1000) に変更してください。
  ```bash
  sudo chown -R 1000:1000 /path/to/project/sessions
  ```
* **セッション間・ユーザー間ファイル隔離**:
  コンテナ起動時、ホスト側のルート保存領域（`RCE_DATA_DIR`）全体ではなく、**セッションごとの個別サブディレクトリ（`<RCE_DATA_DIR>/<session_id>`）のみがコンテナ内の `/mnt/data` にマウント**されます。
  そのため、コンテナ内から他のユーザー・他セッションのディレクトリを閲覧することは構造上不可能です。

## 4. コンテナリソースと保持期間 (TTL) の運用設計

* **コンテナサイズ**:
  * ベースイメージ（`custom-rce-kernel:latest`）: **約 700 MB**（全コンテナで読み取り専用共有）
  * 各コンテナの書き込みレイヤー: **約 70 KB 〜 数 MB 程度**（極めて軽量）
* **TTL 長期保持の妥当性**:
  待機中のアイドルコンテナはメモリ・ディスク負荷が非常に小さいため、会話のコンテキストや作業ファイルを維持するために **`RCE_SESSION_TTL` を長め（例: 4時間〜24時間）に設定して運用することが推奨されます**。
* **TTL 経過後の再生成**:
  TTL 経過によりコンテナが破棄された場合でも、同じチャットで次回コード実行が要求された時点で **新しいサンドボックスコンテナが自動的に即座に作成** されます（ボリュームマウントモード時は過去ファイルも引き継がれます）。

## 5. 関連ドキュメント
* [Sandbox Image Design](./sandbox-image.md) - Dockerfile.rce の構築仕様
* [Configuration Reference](./configuration.md) - 環境変数一覧
