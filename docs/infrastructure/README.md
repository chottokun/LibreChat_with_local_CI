---
type: Index
title: Infrastructure Index
description: Docker Compose構成、サンドボックスイメージ、Caddy SSL/Artifacts、環境変数設定インデックス
status: active
timestamp: 2026-08-14T09:30:00+09:00
tags:
  - infrastructure
  - index
---

# Infrastructure Index

本ディレクトリでは、LibreChat Custom RCE を稼働させるための Docker Compose 構成、コンテナイメージ設計、リバースプロキシおよび SSL/TLS、各種環境変数の設定手順を管理します。

## インフラ構成ページ

* [Docker Setup & Storage Modes](./docker-setup.md) - Docker Compose構成、起動モード、ストレージモード（put_archive vs ボリュームマウント）
* [Sandbox Image Design](./sandbox-image.md) - `Dockerfile.rce` / `Dockerfile.rce.gpu` / `Dockerfile.api` の設計とセキュリティ設定
* [Reverse Proxy & SSL Design (Nginx)](./reverse-proxy.md) - Nginxリバースプロキシ、SAN証明書、WebSocket/SSEストリーミング、将来のOIDC/SSO設計
* [Configuration Reference](./configuration.md) - API環境変数、LibreChat環境変数、`librechat.yaml` 設定一覧

## 関連領域
* [Architecture](../architecture/README.md) - 全体アーキテクチャおよびセキュリティ
* [Domain](../domain/README.md) - ドメインロジックおよびファイル処理
