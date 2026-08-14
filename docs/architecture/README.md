---
type: Index
title: Architecture Index
description: LibreChat Custom RCE のアーキテクチャ方針、設計原則、システム構成インデックス
status: stable
generated:
  by: agent/gemini-3.7-flash
  at: 2026-08-14T09:30:00+09:00
tags:
  - architecture
  - index
---

# Architecture Index

本ディレクトリでは、LibreChat Custom RCE システムの全体アーキテクチャ、並行制御、セキュリティ境界などの設計原則を管理します。

## アーキテクチャ構成ページ

* [System Overview](./overview.md) - システム全体アーキテクチャ、主要コンポーネント構成、リクエスト処理フロー
* [Concurrency Control](./concurrency.md) - `WeakrefRLock` と `pending_sessions` によるスレッドセーフな並行制御とキャパシティ管理
* [Security Model](./security.md) - Docker Socket Proxy、非ルートコンテナ、ネットワーク隔離、CORSホワイトリストなどの多層防御
* [Comprehensive Code Review Report](./review-report.md) - 包括的コードレビューレポート
* [Function Audit Matrix](./detailed-function-audit.md) - 主要関数の不変条件・例外安全性の監査マトリクス
* [Refactoring Proposals & Risk Analysis](./refactoring-proposals.md) - リファクタリング提案と批判的リスク・副作用分析

## 関連領域
* [Domain](../domain/README.md) - ドメインロジックおよびデータ構造
* [Infrastructure](../infrastructure/README.md) - Dockerおよびインフラ構成
