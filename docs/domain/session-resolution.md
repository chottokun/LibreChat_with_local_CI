---
type: Concept
title: Session ID Resolution & Fallback
description: LibreChatのセッションID欠落に対する自動解決優先順位とフォールバック仕様
status: stable
generated:
  by: agent/claude-opus-4.6
  at: 2026-08-20T20:20:00+09:00
tags:
  - domain
  - session
  - fallback
  - librechat-compatibility
---

# Session ID Resolution & Fallback (セッションID解決とフォールバック)

## 1. 概要

LibreChatのクライアント側ツール（`@librechat/agents` 等）では、ファイルを添付しないコード実行時などに、リクエストルートの `session_id` が省略されて送信される仕様上の特性があります。

本APIでは、チャット間のセッション分離を保証しつつ、同一チャット内でのステートフルな実行を維持するため、以下の解決フローを実装しています。

## 2. セッションID解決フロー（`/exec` エンドポイント）

```mermaid
graph TD
    Req["/exec リクエスト受信"] --> Step0{"1. req.session_id / req.entity_id<br>はあるか?"}
    Step0 -- Yes --> UseReq["リクエスト内のセッションIDを採用"]
    Step0 -- No --> Step1{"2. req.files 内に<br>session_id / storage_session_id はあるか?"}
    Step1 -- Yes --> UseFiles["files 内のセッションIDを採用"]
    Step1 -- No --> GenNew["新規セッションID (Nanoid) を生成"]

    UseReq --> Resolve["21文字Nanoid検証 & UUIDマッピング"]
    UseFiles --> Resolve
    GenNew --> Resolve
```

### 優先順位（設計不変条件）
1. **リクエスト直接指定**: `session_id` または `entity_id`。
2. **ファイルメタデータ**: `files` 配下の各要素に含まれる `session_id` もしくは `storage_session_id`。
3. **新規生成**: 上記すべてが欠落した場合、常に新規セッションID (Nanoid) を生成。

> [!IMPORTANT]
> **チャット分離保証**: グローバル変数 `LAST_UPLOADED_SESSION_ID` や `user_{user_id}` による共有フォールバックは、チャット間・ユーザ間のセッション汚染（ファイルやコンテナの混同）を引き起こすため**完全廃止**されました。セッション情報が一切ないリクエスト（`/exec` および `/upload`）は、常に独立した新規セッションを生成します。

## 3. `/upload` エンドポイントのセッション解決

アップロードエンドポイントも同様にチャット間の完全分離を保証します。

```mermaid
graph TD
    Req["/upload リクエスト受信"] --> Check{"entity_id / session_id はあるか?"}
    Check -- Yes --> UseSid["指定されたセッションIDを採用"]
    Check -- No --> GenNew["新規セッションIDを生成"]

    UseSid --> Process["ファイルアップロード処理"]
    GenNew --> Process
```

## 4. LibreChatの実際の送信パターン（ログ実証済み）

| フィールド | 送信状況 | 備考 |
|---|---|---|
| `session_id` | ほぼ常に `None` | LibreChatは `/exec` で `session_id` を送信しない |
| `entity_id` | ほぼ常に `None` | 同上 |
| `user_id` | 常に `None` | 現行のLibreChatでは未送信 |
| `files[].storage_session_id` | ✅ 送信される | RCEレスポンスの `session_id` を次のリクエストで再送 |

このため、同一チャット内でのセッション継続は主に `files[].storage_session_id` に依存しています。

## 5. 関連ドキュメント
* [Nanoid ID Mapping](./nanoid-mapping.md) - 21文字Nanoid変換仕様
* [Concurrency Control](../architecture/concurrency.md) - 並行セッションロック
