# LibreChat ローカル RCE 開発・設計ガイド

本ドキュメントは、**LibreChat_with_local_CI** のコードベースを拡張・保守する開発者（コントリビューター）向けに、内部アーキテクチャ、APIプロトコル、実行環境（RCEカーネル）の拡張方法、およびテスト手順を解説する設計書です。

---

## 1. 全体アーキテクチャ

本リポジトリは、LibreChat の「エージェント機能（Code Interpreter）」から送られるコード実行リクエストを受け取り、ローカルの隔離されたセキュアな Docker コンテナ内で実行して結果を返す **Custom RCE (Remote Code Execution) API サーバー**を実装しています。

```
+------------------+         REST API         +---------------------+
|    LibreChat     | -----------------------> | Code Interpreter API| (main.py)
| (Agent UI / App) | <----------------------- | (FastAPI / Port 8000|
+------------------+     JSON / File stream   +---------------------+
                                                        |
                                                 Docker Socket Proxy
                                                   (Port 2375/内部)
                                                        |
                                                        v
                                              +---------------------+
                                              | Ephemeral Sandboxes |
                                              | [custom-rce-kernel] | (セッション毎に1コンテナ)
                                              +---------------------+
```

### コア技術スタック

| カテゴリ | 技術 |
|---|---|
| API サーバー | FastAPI (Python 3.13+, `main.py`) |
| パッケージ管理 | uv (`pyproject.toml`) |
| コンテナ管理 | Docker Engine + Docker Socket Proxy |
| サンドボックス | `custom-rce-kernel:latest` (Python 3.11-slim ベース) |
| テスト | pytest (26ファイル、164以上の検証ケース) |
| セキュリティ | 非root実行、リソース制限、Docker Socket Proxy による権限分離 |
| 動作確認済み LibreChat | `ghcr.io/danny-avila/librechat:v0.8.6` (2026-06-01 リリース) |

### プロジェクトファイル構成

```
LibreChat_with_local_CI/
├── main.py                     # FastAPI アプリケーション本体（全エンドポイント + KernelManager）
├── pyproject.toml              # API サーバーの依存関係定義 (uv 管理)
├── rce_requirements.txt        # RCE カーネル内の Python パッケージ定義
├── Dockerfile.api              # API サーバー用コンテナイメージ
├── Dockerfile.rce              # RCE サンドボックス用コンテナイメージ
├── Dockerfile.rce.gpu          # GPU 対応 RCE サンドボックス用コンテナイメージ
├── docker-compose.yml          # 標準デプロイ構成（API + Docker Socket Proxy）
├── docker-compose.gpu.yml      # GPU デプロイ構成
├── docker-compose.librechat.yml # LibreChat 統合構成
├── Caddyfile                   # リバースプロキシ設定
├── librechat.yaml              # LibreChat 側の接続設定
├── .env                        # 環境変数定義
├── tests/                      # pytest テストスイート
│   ├── conftest.py             # テスト共通フィクスチャ
│   ├── test_api.py             # API エンドポイントテスト
│   ├── test_kernel_manager.py  # KernelManager ユニットテスト
│   ├── test_path_traversal.py  # パストラバーサル防御テスト
│   ├── test_security_*.py      # セキュリティ関連テスト群
│   ├── test_download_*.py      # ダウンロード機能テスト群
│   ├── test_upload_api.py      # アップロード機能テスト
│   └── ...                     # その他テストファイル
└── sessions/                   # セッションデータの永続化ディレクトリ
```

---

## 2. API プロトコル仕様

FastAPI (`main.py`) は、LibreChat の Code Interpreter 仕様に準拠したインターフェースを提供します。

### 2.1 コード実行: `POST /exec`, `POST /run/exec`

LibreChat からエージェント実行時に送信されるコードを実行します。

**リクエスト形式:**

```json
{
  "code": "print('Hello Dev')",
  "lang": "py",
  "session_id": "user-session-123",
  "user_id": "user-456",
  "files": [],
  "args": []
}
```

**処理フロー:**

1. 送信された `session_id` に紐づく専用コンテナ（例: `rce_<uuid>_<hash>`）が存在するか確認
2. 存在しない場合は、`RCE_IMAGE_NAME`（既定: `custom-rce-kernel:latest`）ベースの新コンテナを即時スピンアップ
3. `docker exec` を用いてコンテナ内部でコードを評価（Python の場合は最終式の自動表示ラッピングあり）
4. 実行後の出力（stdout / stderr）を取得し、生成されたファイル一覧とともに返却

**レスポンス形式:**

```json
{
  "stdout": "Hello Dev\n",
  "stderr": "",
  "exit_code": 0,
  "output": "Hello Dev\n",
  "result": "Hello Dev\n",
  "status": "success",
  "session_id": "nanoid-session-abc",
  "files": [
    {
      "id": "nanoid-file-id",
      "name": "output.csv",
      "url": "/api/files/code/download/nanoid-session-abc/nanoid-file-id",
      "type": "text/csv"
    }
  ],
  "images": []
}
```

**対応言語:** `python` / `py`, `bash` / `sh`, `r`

### 2.2 ファイルアップロード: `POST /upload`

アップロードされたファイルをセッションごとの永続ディレクトリに配置します。

- `entity_id` / `session_id` / クエリパラメータの3種類でセッション指定をサポート
- ディレクトリトラバーサル脆弱性を防ぐため、ファイルパスは `os.path.basename()` で厳格にサニタイズ
- ボリュームマウントモード（高速）と `put_archive` モード（フォールバック）を自動選択

### 2.3 ファイル一覧: `GET /files/{session_id}`

セッションのサンドボックス内にあるファイル一覧を返却します。

### 2.4 ファイルダウンロード

複数のルートパターンをサポートしています:

| エンドポイント | 用途 |
|---|---|
| `GET /download?session_id=...&filename=...` | クエリパラメータ方式 |
| `GET /run/download?session_id=...&filename=...` | 同上（`/run` プレフィックス付き） |
| `GET /download/{session_id}/{filename}` | パスパラメータ方式 |
| `GET /run/download/{session_id}/{filename}` | 同上（`/run` プレフィックス付き） |
| `GET /api/files/code/download/{session_id}/{filename}` | LibreChat ネイティブ形式 |

- NanoID ベースのファイルID → 実ファイル名の解決を自動実行
- 日本語ファイル名は RFC 5987 準拠の `filename*=utf-8''...` ヘッダーで安全に送信
- CSV は `text/plain` で返却し、Chrome のセキュリティブロックを回避

### 2.5 ヘルスチェック: `GET /health`

```json
{"status": "ok", "mode": "docker-sandboxed"}
```

---

## 3. KernelManager の設計

`KernelManager` クラス（`main.py` 内）は、セッション管理とコンテナライフサイクルの中核です。

### 3.1 セッション ID マッピング

```
LibreChat からの session_id (NanoID 等)
    ↓ sanitize_id() でサニタイズ
    ↓ get_or_create_session_mapping() で解決
内部 UUID セッション ID (コンテナ名・ディレクトリ名に使用)
```

- `nanoid_to_session`: 外部ID → 内部UUID の正引きマップ
- `session_to_nanoid`: 内部UUID → 外部ID の逆引きマップ
- `file_id_map`: セッション毎の NanoID ファイルID → 実ファイル名 マップ

### 3.2 コンテナライフサイクル

1. **作成**: `get_or_create_container()` で遅延生成。最大 `RCE_MAX_SESSIONS` 個まで
2. **リソース制限**: メモリ上限 (`RCE_MEM_LIMIT`)、CPU 制限 (`RCE_CPU_LIMIT`)、ネットワーク無効化（デフォルト）
3. **自動復旧**: `recover_containers()` でAPI再起動時に既存コンテナを再認識
4. **TTL 管理**: `cleanup_loop()` が60秒間隔で実行。`RCE_SESSION_TTL`（デフォルト3600秒）超過のセッションを自動削除
5. **ファイル転送**: ボリュームマウントが有効なら直接 I/O、無効なら `put_archive` / `get_archive` でコンテナと通信

### 3.3 セッションフォールバックロジック

LibreChat が `session_id` を消失・未送信の場合のフォールバック優先順:

1. `req.files[0].session_id` または `storage_session_id` から抽出
2. `req.user_id` から `user_{user_id}` として生成
3. 直近5分以内のアップロード実績がある場合、`LAST_UPLOADED_SESSION_ID` を再利用
4. いずれも不可の場合、新規 NanoID を自動生成

> **注意:** このフォールバックロジック周辺をリファクタリングする際は、ログ出力（`Received key: None` 等のデバッグメッセージ）の挙動に影響を及ぼさないよう配慮してください。

---

## 4. RCE カーネル（実行用サンドボックス）の拡張

コードが実際に走るコンテナイメージは `Dockerfile.rce` で定義されています。

### 4.1 パッケージの追加方法

1. `rce_requirements.txt` に必要なライブラリを記述
2. 以下のコマンドを実行してカーネルを再ビルド:

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
```

**現在インストール済みのパッケージ:**

- `pandas`, `numpy`, `scipy` — データ分析
- `matplotlib`, `seaborn` — データ可視化
- `japanize-matplotlib` — 日本語フォント対応

> **開発者向け注記:** 日本語フォントを伴うデータ分析（Matplotlib によるグラフ描画など）の文字化けに対処するため、イメージのビルドプロセスで `japanize-matplotlib` が `sitecustomize.py` 経由で自動インポートされます。また、`fonts-ipafont-gothic` フォントパッケージも含まれています。

### 4.2 GPU 対応カーネルの開発

CUDA 対応モデルや重い数値計算を RCE 内で開発・テストする場合は、GPU 用の構成を使用します:

```bash
# GPU カーネルのビルド
docker build -f Dockerfile.rce.gpu -t custom-rce-kernel:latest .

# GPU 構成でのデプロイ
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

- ベースイメージ: `nvidia/cuda:12.1.0-base-ubuntu22.04`
- 環境変数 `RCE_GPU_ENABLED=true` の設定が必要

---

## 5. 環境変数リファレンス

| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `LIBRECHAT_CODE_API_KEY` | *(必須)* | API 認証キー。認証が有効な場合は設定必須 |
| `DISABLE_CODE_API_AUTH` | `false` | `true` で認証を無効化（開発・テスト用） |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | サンドボックスに使用する Docker イメージ名 |
| `RCE_DATA_DIR` / `RCE_DATA_DIR_HOST` | *(未設定)* | ホスト側のセッションデータディレクトリ |
| `RCE_DATA_DIR_INTERNAL` | `/app/shared_volumes/sessions` | API コンテナ内のセッションデータパス |
| `RCE_SESSION_TTL` | `3600` | セッションの生存期間（秒） |
| `RCE_MAX_SESSIONS` | `100` | 同時実行可能な最大セッション数 |
| `RCE_MEM_LIMIT` | `512m` | コンテナのメモリ上限 |
| `RCE_CPU_LIMIT` | `500000000` | CPU 制限（ナノ秒単位、0.5 CPU） |
| `RCE_NETWORK_ENABLED` | `false` | サンドボックスのネットワークアクセス |
| `RCE_GPU_ENABLED` | `false` | GPU デバイスのパススルー |
| `DOCKER_HOST` | `tcp://docker-proxy:2375` | Docker デーモンの接続先 |

---

## 6. ローカル開発環境のセットアップ

### 6.1 FastAPI サーバーのローカル実行

コンテナ内部ではなく、ホスト側で API コード (`main.py`) を直接デバッグ・開発する場合の手順です。

```bash
# 仮想環境の構築と依存パッケージの同期
uv sync

# 環境変数の構成（検証時は一時的に認証を無効化するとスムーズです）
export LIBRECHAT_CODE_API_KEY="dev-secret-key"
export DISABLE_CODE_API_AUTH="true"
export RCE_IMAGE_NAME="custom-rce-kernel:latest"

# 開発用サーバーの起動（ホットリロード有効）
uv run uvicorn main:app --reload --port 3080
```

### 6.2 Docker Compose でのフルスタック起動

```bash
# RCE カーネルのビルド
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .

# API + Docker Socket Proxy の起動
docker compose up -d
```

---

## 7. テスト駆動開発 (TDD) と CI

本プロジェクトの堅牢性は、26ファイル・164以上の pytest 検証ケースによって保証されています。コード変更時は、必ずテストを実行してデグレーションがないか確認してください。

### 7.1 テストの実行

ホスト OS に Python 3.13+ および Docker 環境があることを確認し、テストを実行します。

テストは **2段階** で実行する必要があります。認証機能をテストするケースと、認証を無効化した状態でその他機能をテストするケースで設定が異なるためです。

```bash
# ステップ1: 認証が必要なテスト（APIキーを有効にした状態で実行）
LIBRECHAT_CODE_API_KEY=test-dev-key uv run pytest tests/test_auth_unit.py tests/test_api.py -v

# ステップ2: その他すべてのテスト（認証を無効にした状態で実行）
LIBRECHAT_CODE_API_KEY=test-dev-key DISABLE_CODE_API_AUTH=true uv run pytest tests/ --ignore=tests/test_auth_unit.py -v
```

> **注意:** 両ステップすべてが合格することを確認してください。`DISABLE_CODE_API_AUTH=true` を設定したまま認証テストを実行すると、401 が期待される箇所で 200 が返るため、意図的に失敗します。

### 7.2 必須のテスト検証項目

新規機能やエンドポイントの変更パッチをコミットする際は、以下のカテゴリに対するテストケースを `tests/` 内に追加することを推奨します:

- **多言語実行テスト:** Python、Bash、R が想定通りに動作するか
- **境界セキュリティ検証:** パストラバーサル（`../../` 等の悪意ある入力）によるホストファイルシステムへのアクセスが完全に遮断されているか
- **高負荷セッション・フォールバック:** 多数のセッション（コンテナ）が並列で動いた際、スレッドセーフにファイルマッピングとクリーンアップが行われるか
- **セッション ID 解決:** NanoID ↔ 内部 UUID のマッピングが正しく機能するか
- **認証フォールバック:** `X-API-Key`, `Authorization: Bearer`, クエリパラメータの全パスが正しく動作するか

---

## 8. セキュリティ設計

### 8.1 Docker Socket Proxy

本 API は、ホストの Docker ソケット（`/var/run/docker.sock`）に直接触れず、**制限付きプロキシサーバー** (`tecnativa/docker-socket-proxy`) を仲介させてコンテナの作成・実行権限のみを解放するアプローチをとっています。

```yaml
# docker-compose.yml での権限設定
environment:
  - CONTAINERS=1    # コンテナ操作: 許可
  - EXEC=1          # コンテナ内実行: 許可
  - POST=1          # POST リクエスト: 許可
  - BUILD=0         # イメージビルド: 拒否
  - IMAGES=0        # イメージ操作: 拒否
  - NETWORKS=0      # ネットワーク操作: 拒否
  - VOLUMES=0       # ボリューム操作: 拒否
```

開発段階でも、Docker ソケットの直接マウントによるセキュリティ侵害リスクに配慮した設計を維持してください。

### 8.2 サンドボックスの隔離

各コンテナには以下のセキュリティ制約が適用されます:

- **非 root ユーザー** (`sandboxuser`, UID 1000) で実行
- **メモリ・CPU 制限** による DoS 対策
- **ネットワーク無効化**（デフォルト）による情報漏洩防止
- **自動削除** (`remove=True`) によるコンテナ残留防止
- **入力サニタイズ** (`sanitize_id()`) によるインジェクション防止

### 8.3 セキュリティヘッダー

`SecurityHeadersCORSMiddleware` により、ダウンロード以外の全レスポンスに以下のヘッダーを付与:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Referrer-Policy: no-referrer`

---

## 9. 動作確認済み環境

以下の構成でエンドツーエンドの動作検証を実施済みです。

| コンポーネント | バージョン / イメージ | 確認日 |
|---|---|---|
| LibreChat | `ghcr.io/danny-avila/librechat:v0.8.6` | 2026-06-06 |
| LibreChat RAG API | `ghcr.io/danny-avila/librechat-rag-api-dev-lite:latest` | 2026-06-06 |
| Sandpack Bundler | `ghcr.io/librechat-ai/codesandbox-client/bundler:latest` | 2026-06-06 |
| Code Interpreter API | `librechat_with_local_ci-code-interpreter-api` (本リポジトリ) | 2026-06-06 |
| RCE カーネル | `custom-rce-kernel:latest` (Python 3.11-slim ベース) | 2026-06-06 |
| Docker Socket Proxy | `tecnativa/docker-socket-proxy` | 2026-06-06 |
| MeiliSearch | `getmeili/meilisearch:v1.7.3` | 2026-06-06 |
| pgvector | `pgvector/pgvector:0.8.0-pg15-trixie` | 2026-06-06 |

### 動作確認済みの主要機能

- ✅ **Code Interpreter（Python コード実行）**: エージェントによる Python コードの実行、stdout/stderr の取得
- ✅ **Artifacts 機能**: LibreChat v0.8.6 でのアーティファクト（HTML/TSX プレビュー）表示
- ✅ **Sandpack Bundler（ローカル）**: SSL モード（`ssl-mode` プロファイル）での Caddy + Sandpack ローカルバンドラー動作
- ✅ **セッションフォールバック**: `session_id: null` 送信時の自動セッション生成
- ✅ **認証機能**: `X-API-Key` ヘッダー、`Authorization: Bearer` トークン、クエリパラメータの3方式すべて
- ✅ **セキュリティヘッダー**: 全レスポンスへのセキュリティヘッダー付与
- ✅ **パストラバーサル防御**: `../../` 等の悪意ある入力のブロック

### 既知の警告（動作上の問題ではない）

- **`RAG API is not reachable at undefined`**: LibreChat 起動時ログに出力されることがあるが、RAG API コンテナが同一ネットワーク内で起動していれば実運用上は問題なし。
- **`Failed to fetch models from openAI API (401)`**: OpenAI API キーが本番キーでない場合（ダミーキー使用時）に定期的に出力される。Ollama や External API が正しく設定されていれば、他のモデルは正常に利用可能。
- **`sandpack-bundler (unhealthy)`**: `ssl-mode` プロファイルで起動している場合のヘルスチェック設定に起因。HTTP ヘルスチェックが HTTPS リダイレクトで失敗するため。動作自体は問題なし。

### LibreChat バージョンの更新手順

LibreChat の新バージョンへ更新する際は、以下の手順を踏んでください。

1. [docker-compose.librechat.yml](docker-compose.librechat.yml) の `librechat` サービスのイメージタグを更新する
2. フルスタックを起動して手動動作確認を実施する
3. pytest テストスイートを2段階で全件実行し、合格を確認する
4. 本ドキュメントの「動作確認済み環境」表を更新する