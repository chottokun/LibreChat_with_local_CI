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

### A. フルスタック構成 (LibreChat + API + DB)
1. **設定ファイルの準備**:
   ```bash
   cp .env.librechat .env
   # JWT_SECRET, CREDS_KEY, LIBRECHAT_CODE_API_KEY を設定
   ```
2. **サンドボックスイメージのビルド**:
   ```bash
   docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
   ```
3. **起動**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
   ```

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

### ボリュームマウント時の権限設定
ボリュームマウントモードを使用する場合は、ホスト側ディレクトリの所有者を `sandboxuser` (UID 1000) に変更してください。
```bash
sudo chown -R 1000:1000 /path/to/project/sessions
```

## 4. 関連ドキュメント
* [Sandbox Image Design](./sandbox-image.md) - Dockerfile.rce の構築仕様
* [Configuration Reference](./configuration.md) - 環境変数一覧
