---
type: Report
title: Session Isolation Investigation & Resolution Report
description: チャット間・ユーザー間における/mnt/data/データ残留問題の根本原因調査結果、徹底的な分離設計仕様、およびエンタープライズオンプレミス環境での検証報告
status: stable
generated:
  by: agent/claude-opus-4.6
  at: 2026-08-20T21:30:00+09:00
tags:
  - report
  - session-isolation
  - security
  - enterprise
  - domain
---

# Session Isolation Investigation & Resolution Report (セッション分離徹底調査・対策報告書)

## 1. 概要

LibreChat Code Interpreter API (Custom RCE) において、「別チャットを開いた際に `/mnt/data/` ディレクトリ内に前チャットのファイルやデータが残留する」現象について、原因の徹底調査とアーキテクチャ再設計を実施しました。

本ドキュメントは、問題発生の根本原因、新設計仕様、LibreChat とのプロトコル整合性、エンタープライズオンプレミス環境におけるベストプラクティス比較、およびテスト検証結果を後からの振り返り・監査用に記録するレポートです。

---

## 2. 根本原因の分析 (Root Cause Analysis)

調査の結果、別チャット間でのセッション汚染・ファイル残留は、**2点の共有フォールバック処理**によって引き起こされていました。

### 原因 1: `/upload` エンドポイントでの `LAST_UPLOADED_SESSION_ID` グローバルフォールバック
- **発生メカニズム:**
  - LibreChat でファイルアップロードを行う際、リクエストフォームに `session_id` や `entity_id` が含まれない仕様があります。
  - 従来の実装では、直近5分以内に別チャット (Chat 1) でファイルがアップロードされていた場合、`/upload` がグローバル変数 `LAST_UPLOADED_SESSION_ID` (Chat 1 のセッションID) を自動的に再利用していました。
- **影響:**
  - Chat 2 でアップロードされたファイルが Chat 1 のサンドボックスディレクトリ (`/mnt/data/`) に書き込まれ、LibreChat 側に Chat 1 の `session_id` が返却されました。
  - Chat 2 の次回コード実行 (`/exec`) が Chat 1 の Docker コンテナ・ボリュームにルーティングされ、Chat 1 のデータが残留・漏洩していました。

### 原因 2: `_get_effective_session_id()` における `user_{user_id}` フォールバック
- **発生メカニズム:**
  - `/exec` リクエストにおいて `user_id` が送信され、`session_id` や `files` 情報がない場合、`user_{user_id}` を共通セッションIDとしてバインドしていました。
- **影響:**
  - `user_id` は同一ユーザーのすべてのチャットスレッドで同一であるため、Chat 1 と Chat 2 が双方とも同じコンテナ `user_{user_id}` を共有し、`/mnt/data/` の状態がそのまま維持されていました。

---

## 3. ベストプラクティスに基づく徹底分離仕様 (Strict Isolation Invariants)

チャット間およびユーザー間の完全な隔離を保証するため、以下の設計不変条件を確立・実装しました。

### A. セッション解決の解決順序 (Priority Order)
1. **明示的なリクエストパラメータ:** `session_id` または `entity_id`
2. **ファイルメタデータコンテキスト:** リクエストに含まれる `files[].storage_session_id` または `files[].session_id`
3. **新規独立生成 (徹底隔離):** 上記が一切存在しない場合、**常に独立した 21文字の新規 Nanoid** を生成する。

> [!CAUTION]
> グローバル変数 `LAST_UPLOADED_SESSION_ID` および `user_{user_id}` による共有フォールバックロジックは完全廃止されました。セッションIDのないすべてのアップロード・実行リクエストは独立した sandbox を生成します。

### B. LibreChat ターン間継続性の仕組み
- **ファイルアタッチ時:** LibreChat はアップロード応答時やコード実行応答時に返却された `storage_session_id` を、次回ターンにおける `files[].storage_session_id` として自動返送します。これにより、同一チャット内でのターン間状態（`/mnt/data/`）は完璧に維持されます。
- **別チャット開始時:** 新しいチャットスレッドでは `storage_session_id` が引き継がれないため、完全な新規 Nanoid セッションが生成されます。他チャットのコンテナやボリュームディレクトリには物理的にアクセス不可能です。

---

## 4. エンタープライズオンプレミス環境における比較分析 (Enterprise Best Practices)

金融・医療・官公庁等のオンプレミス閉域網（エアギャップ環境）における Code Interpreter 運用において、単一コンテナで固定ホストディレクトリ（例: `./data:/mnt/data`）を共有する簡易構成は、**「全チャット・全ユーザーで同一領域が共有され、重大な情報漏洩事故を起こす」** ため厳禁です。

本リポジトリのアーキテクチャモデル（モデル B）と公式 ClickHouse マイクロサービスモデル（モデル A）の比較は以下の通りです。

| 観点 | モデル A: 公式マイクロサービス構成 | モデル B: 本リポジトリ (Dynamic Docker Orchestrator) |
|---|---|---|
| **コンポーネント** | API Gateway + Worker (NsJail) + Redis + MinIO (S3) | FastAPI Gateway + KernelManager + Docker Socket Proxy |
| **ファイル隔離方式** | MinIO バケット `/code-interpreter-files/{session_id}/` | ホストボリューム `/app/shared_volumes/sessions/{session_uuid}` |
| **ライフサイクル** | Worker が S3 から Hydrate → 実行 → 成果物を S3 退避 → 即座破棄 | 動的 Docker コンテナ + セッション別ディレクトリバインド (`RCE_SESSION_TTL` 破棄) |
| **閉域網運用性** | ミドルウェア (S3, Redis) 追加が必要 | 単一 `docker compose` で完結（追加 DB/S3 不要で軽量） |
| **チャット間分離** | S3 の `{session_id}` パス分離により達成 | セッション固有の Nanoid → UUID 隔離ディレクトリマウントにより達成 |

### セキュリティの4つの柱 (4 Pillars of Security) の適合性

1. **柱 1: ネットワーク完全閉域化 (SSRF・横展開対策)**
   - サンドボックスコンテナは `network_disabled: true` で作成。コードからの外部 LAN/WAN や他コンテナへの SSRF 攻撃をカーネルレベルでブロック。
2. **柱 2: サンドボックスおよびカーネル境界隔離**
   - 非特権ユーザー (UID 1000) で実行。ホストの `/var/run/docker.sock` を直接マウントさせず、`docker-socket-proxy` 経由で制限付き API のみ許可。
3. **柱 3: リソース制限と DoS (Fork Bomb) 耐性**
   - `pids_limit`, `mem_limit` (512m), `nano_cpus` (0.5 CPU) および `RCE_SESSION_TTL` によるリソース枯渇・DoS 防御。
4. **柱 4: オフライン・パッケージ事前焼付 (Pre-baked Packages)**
   - エアギャップ環境向けに主要解析パッケージ (pandas, numpy, matplotlib, seaborn, scikit-learn 等) および日本語フォント (IPAフォント, japanize-matplotlib) をビルド時に同梱。

---

## 5. 変更ファイルと影響範囲 (Summary of Changes)

| ファイル | 変更内容 |
|---|---|
| `main.py` | `LAST_UPLOADED_SESSION_ID` / `LAST_UPLOAD_TIME` の撤廃。`/upload` および `_get_effective_session_id` での共有フォールバック削除 |
| `AGENTS.md` | §5.1 コア設計仕様に「グローバル・ユーザー間共有フォールバックの禁止」を明記 |
| `docs/domain/session-resolution.md` | セッション解決フローの Mermaid ダイアグラムおよび仕様記述を更新 |
| `README.md` / `docs/architecture/overview.md` | セッション分離仕様とシーケンス図を最新化 |
| `tests/test_upload_api.py` | 単独アップロードの独立セッション生成テストに更新 |
| `tests/test_upload_extended.py` | 並行・連続アップロード時の独立セッション生成検証、チャット間データ隔離テスト (`test_chat_isolation_prevents_cross_chat_data_spill`) 追加 |
| `tests/test_tdd_improvements.py` | `user_id` 送信時の独立セッション生成テストに更新 |
| `tests/test_librechat_e2e_thorough.py` | `files[].storage_session_id` を経由した同一チャット内多ターン継続性テスト追加 |

---

## 6. 検証結果 (Verification Results)

- **自動テスト結果:** `308 passed` (全テストクリア)
- **環境モード:** 認証有効モード (`DISABLE_CODE_API_AUTH=false`) および 認証無効モード (`DISABLE_CODE_API_AUTH=true`) の双方で全件通過を確認。
