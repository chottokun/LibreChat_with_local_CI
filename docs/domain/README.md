---
type: Index
title: Domain Index
description: LibreChat Custom RCE のドメインロジック、データモデル、セッション解決、実行管理インデックス
status: stable
generated:
  by: agent/gemini-3.7-flash
  at: 2026-08-14T09:30:00+09:00
tags:
  - domain
  - index
---

# Domain Index

本ディレクトリでは、LibreChatのクライアント仕様やCode Interpreterプロトコルに対応するためのドメインロジック、データ構造、セッションライフサイクル管理について解説します。

## ドメイン概念ページ

* [Session ID Resolution & Fallback](./session-resolution.md) - セッションIDの優先順位自動解決仕様
* [Session Isolation Investigation Report](./session-isolation-report.md) - チャット間・ユーザー間データ残留問題の調査・対策報告書
* [Nanoid ID Mapping](./nanoid-mapping.md) - LibreChat `isValidID` (21文字Nanoid) バリデーション準拠と内部UUID双方向マッピング
* [File Handling & UTF-8](./file-handling.md) - $O(N)$ ファイルマッピング、日本語UTF-8ファイル名処理および `Content-Disposition`
* [Multi-Language Code Execution](./code-execution.md) - Python/Bash/R 多言語実行、AST解析による末尾評価式出力、Matplotlib 日本語描画

## 関連領域
* [Architecture](../architecture/README.md) - システム全体アーキテクチャ
* [Infrastructure](../infrastructure/README.md) - インフラおよびDocker設定
