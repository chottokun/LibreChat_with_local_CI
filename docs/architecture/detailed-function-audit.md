---
type: Concept
title: Detailed Function Audit Matrix
description: main.py および KernelManager の主要関数の不変条件、スレッドセーフティ、例外安全性の監査マトリクス
status: active
timestamp: 2026-08-14T10:30:00+09:00
tags:
  - architecture
  - audit
  - security
  - functions
---

# LibreChat Code Interpreter API: Core Function Audit Matrix

本ドキュメントは、`main.py` および `KernelManager` の主要関数に対する設計制約、並行性不変条件、例外安全性、パスセキュリティの監査結果をまとめたものです。

---

## 1. Meticulous Function Audit Matrix

| 関数名 | 所在地 | 主要な不変条件 | エッジケースの挙動 | スレッドセーフティ戦略 | セキュリティ / パス保護 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `get_api_key` | `main.py` | 4つのフォールバックでAPIトークンを検証。 | テスト用フラグ有効時は `"disabled"` を返却。 | 純粋関数（Stateless）。 | `secrets.compare_digest` でタイミング攻撃を防御。 |
| `wrap_code` | `main.py` | AST解析により最終行の式ステートメントをラップ。 | パースエラー時は元の文字列に安全にフォールバック。 | スレッドセーフ、状態非保持。 | サンドボックス外で安全に実行。 |
| `sanitize_id` | `main.py` | 英数字、`-`、`_` のみを許可。 | 入力が None/空の場合は `""` を返却。 | スレッドセーフ、状態非保持。 | ディレクトリ区切り文字を完全排除してトラバーサル防御。 |
| `resolve_session_id` | `KernelManager` | NanoID セッションを内部 UUID にデコード。 | 不正な文字列はサニタイズし、同一性にフォールバック。 | `self.lock` 下で同期。 | ベースディレクトリ外への脱出を防止。 |
| `resolve_download_ids` | `KernelManager` | セッションIDを正規化し仮想ファイルNanoIDをマッピング。 | サニタイズ後が空の場合は 400 を送出。 | `self.lock` 下で同期。 | 相対パスを正規化（`os.path.normpath` / `Path`）。 |
| `get_or_create_container`| `KernelManager` | 起動中インスタンス取得、停止コンテナの復元。 | Docker デーモンが `NotFound` の場合は再作成。 | 二重ロック（グローバルロック + `WeakrefRLock`）。 | 指定されたラベル内でコンテナを安全に分離。 |
| `start_new_container` | `KernelManager` | `RCE_MAX_SESSIONS` 上限内で新規コンテナを作成。 | キャパシティ上限時は 503 を送出。 | `self.pending_sessions` と同期。 | 環境変数・メモリ・CPU制限を動的に適用。 |
| `_prepare_volumes` | `KernelManager` | ボリュームマッピングモードのホスト境界を設定。 | `RCE_DATA_DIR_INTERNAL` 内でパスを解決。 | `self.lock` およびローカルスコープ下で同期。 | 厳格なディレクトリトラバーサル検証。 |
| `upload_files_batch` | `KernelManager` | 並行非同期読み取りによるバッチ書き込み。 | 空ファイル名を安全に除外。 | `to_thread` 経由でブロックI/Oをスレッドプールにオフロード。 | 書き込み先をサンドボックスフォルダ内に厳格制限。 |
| `download_file` | `KernelManager` | ホストパス解決またはコンテナからの `get_archive`。 | ドット相対 `..` フラグメントには 400 を送出。 | ローカライズされたスレッドコンテキスト内で同期。 | 親ディレクトリ継承を明示的に検証。 |
| `list_files` | `KernelManager` | ドット隠しフォルダ/ファイルを除外した再帰的探索。 | JSONパース失敗時は行分割テキストを返却。 | インスタンスコンテキストごとに同期。 | サンドボックス内 `/mnt/data` に厳格制限。 |
| `execute_code` | `KernelManager` | ラップされたコードを一時ファイルに配置して実行。 | `finally` で一時コードファイルを確実に削除。 | 並行タスク委譲によるスレッドセーフティ。 | 引数脱出を防止した `exec_run` 実行。 |

---

## 2. In-Depth Quality Verification

### 2.1 スレッドセーフティモデルの評価
`KernelManager` は **二重ロックモデル** を採用しています：
1. **Global Lock (`self.lock`)**: マッピングの更新やセッション検索などのアトミックな辞書操作に使用。
2. **Session-Level Lock (`WeakrefRLock`)**: `weakref.WeakValueDictionary` 内に保持。複数リクエストが異なるセッションを対象とする場合は Docker デーモン呼び出しを並行実行し、同一セッションを対象とする場合は順序立てて待機することで、重複起動を防止。

### 2.2 パスサニタイズの多層防御
1. **IDレベル**: `sanitize_id` が `/` や `\` を完全に除去。
2. **エンドポイントレベル**: `Path.resolve()` および `Path.is_relative_to` によるパス解決境界チェックを適用。
