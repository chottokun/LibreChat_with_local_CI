# LibreChat Code Interpreter API (Custom RCE)

LibreChatにコード実行機能を提供する、サンドボックス型のCode Interpreter APIです。隔離されたDockerコンテナ群をセッションごとに動的に管理し、安全にコードを実行するためのバックエンドを提供します。

## 概要

本APIは、LibreChatのCode Interpreter仕様に準拠したエンドポイント（`/exec`, `/upload`, `/download`, `/files`）を提供します。隔離環境として専用のDockerイメージを使用し、リソース制限やネットワーク遮断を施した状態でユーザーのコードを実行します。

クラウドプロバイダー（Gemini, OpenAI等）のAPI、およびローカルLLM（Ollama等）のいずれの構成でも利用可能です。

### 本リポジトリの特徴と強み (設計思想)

* **1台の Docker で完結するシンプル・軽量構成**:
  公式の Code Interpreter（`ClickHouse/code-interpreter`）が前提とする Redis（ジョブキュー）や S3 互換オブジェクトストレージ（MinIO等）などの追加ミドルウェアを必要とせず、単一の Docker 環境（`docker compose`）だけでシンプル・安全・高速に動作します。
* **対話継続性を守るセッションID自動フォールバック**:
  LibreChat のクライアント・エージェント側でファイル未添付時などに `session_id` が省略されて送信された場合でも、`user_id` や直近アップロード履歴から自動的にセッションを復元・バインドし、変数の永続性（ステートフル実行）を維持します。
* **日本語ファイル名 (UTF-8) の完全対応**:
  RFC 5987 に準拠した `filename*` エンコード処理により、日本語名を含む生成グラフやアップロードファイルを文字化けなく安全に扱えます。
* **オフライン / オンプレミス環境での Artifacts (React UI 描画) 連携**:
  同梱された Sandpack Bundler および Nginx リバースプロキシ（SSL/TLS モード）により、完全ローカル・オフライン環境でも React や HTML プレビューを即時レンダリング可能です。

---

## 主要な機能と仕様

- **多言語対応**: Pythonに加え、BashおよびR言語の実行に対応しています。
- **グラフ自動インライン描画**: MatplotlibやSeaborn等で生成されたグラフ画像（`.png`, `.jpg`, `.svg`, `.webp`）を自動検知・Base64エンコードし、LibreChatのチャットUI上に即時インライン表示。
- **サンドボックス隔離**: 各セッションはメモリとCPU制限が課された独立した非ルート（`sandboxuser: 1000`）Dockerコンテナ内で実行されます。
- **セッション永続性**: メッセージ間でのファイルシステムの状態および深い階層のディレクトリ構造を維持します。
- **堅牢な並行制御**: セッション個別ロック（`WeakrefRLock`）および起動中セッションの追跡（`pending_sessions`）により、最大容量制限時のレースコンディションを完全に防御。
- **多層防御セキュリティ**:
  - `LIBRECHAT_CODE_API_KEY` によるタイミング攻撃耐性認証（`secrets.compare_digest`）。
  - Docker Socket Proxyを介した最小権限Docker APIアクセス（ホストソケットの直接マウント禁止）。
  - `tarfile`（`put_archive`）による安全な一時スクリプト注入と実行後の自動削除（コマンドラインインジェクション防止）。
  - `sanitize_id` / `Path.is_relative_to` による多層ディレクトリトラバーサル防御。
  - セキュアHTTPレスポンスヘッダー（HSTS, nosniff, DENY, XSS-Protection）。
  - CORSでのワイルドカード `'*'` 使用の拒否および明示的なホワイトリストの厳格な検証。
- **効率的なマッピング**: セッションごとのファイルID管理を $O(N)$ で処理し、LibreChatの21文字Nanoid検証仕様に完全準拠。
- **Nginx リバースプロキシ / SSL / Artifacts 連携**: SAN対応自己署名/正式CA証明書によるHTTPS終端、および Sandpack Bundler（ポート 8443）による React/HTML UI 描画に対応。
- **GPUサポート**: CUDA対応イメージ（`Dockerfile.rce.gpu`）を用いたGPU計算をサポート（オプション）。

## 必須要件

- **Docker**: エンジンが稼働していること。
- **Python 3.13+**: API本体の実行に必要（ローカル開発時のみ）。
- **uv**: パッケージおよび仮想環境管理（推奨）。

---

## セットアップ手順

### A. フルスタック構成 (LibreChat + API + DB + Nginx)

1.  **環境変数の設定**:
    ```bash
    cp .env.librechat .env
    ```
    `.env` 内の `JWT_SECRET`, `CREDS_KEY`, `LIBRECHAT_CODE_API_KEY` を必ず一意の値に更新してください。

2.  **実行イメージの準備**:
    ```bash
    docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
    ```

3.  **SSL/TLS 証明書の準備**:
    自己署名証明書（自己認証）を使用する場合は、同梱のスクリプトで SAN（`localhost`, `127.0.0.1`, ホストLAN内IP）を含む証明書を自動生成します：
    ```bash
    bash certs/generate_cert.sh
    ```
    > **Note**: 商用CA / Let's Encrypt / 社内PKI などの正式な証明書を使用する場合は、証明書・秘密鍵を `./certs/server.crt` および `./certs/server.key` に配置してください。詳細な入れ替え手順は [リバースプロキシ & SSL設計 (docs/infrastructure/reverse-proxy.md)](./docs/infrastructure/reverse-proxy.md) を参照してください。

4.  **起動 (SSL/TLS リバースプロキシ推奨)**:
    Nginx リバースプロキシ経由で HTTPS (443) および Sandpack Bundler (8443) を有効化して起動します。

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
    * **注意**: セキュリティ保護のため、LibreChat 本体のポートはホストマシンのループバック (`127.0.0.1:3000`) にのみバインドされています。外部の別PCやスマホ等のブラウザからアクセスする場合は、上記 **SSL/TLS モード (`--profile ssl-mode`)** をご使用ください。
    </details>

### B. API単体での起動 (既存のLibreChatと連携)

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
docker compose up -d --build
```
LibreChat側の `.env` で `LIBRECHAT_CODE_BASEURL` と `LIBRECHAT_CODE_API_KEY` を設定してください。

### C. GPU対応構成 (オプション)

```bash
docker build -f Dockerfile.rce.gpu -t custom-rce-kernel:gpu .
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## 環境変数 (Configuration)

| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `LIBRECHAT_CODE_API_KEY` | (必須) | APIアクセス認証用の共有キー。 |
| `DISABLE_CODE_API_AUTH` | `false` | `true` に設定するとAPIキーの認証を一時的に無効化（スキップ）します。テスト環境や一部のバグ回避用。 |
| `DOCKER_HOST` | (環境依存 / `tcp://docker-proxy:2375`) | Docker Socket Proxy またはホストデーモンの接続先。 |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | サンドボックスコンテナに使用するイメージ。 |
| `RCE_GPU_ENABLED` | `false` | `true` に設定すると NVIDIA GPU パススルーを有効化。 |
| `RCE_MEM_LIMIT` | `512m` | コンテナあたりのメモリ上限。 |
| `RCE_CPU_LIMIT` | `500000000` | コンテナあたりのCPU制限 (0.5 CPU)。 |
| `RCE_MAX_SESSIONS` | `100` | 最大同時セッション数。 |
| `RCE_SESSION_TTL` | `3600` | アイドルセッションの自動破棄までの生存時間（秒）。 |
| `RCE_NETWORK_ENABLED` | `false` | サンドボックス内からの外部通信許可（セキュリティ上 `false` 推奨）。 |
| `RCE_DATA_DIR` | (なし) | ホスト側のデータ保存先パス（ボリュームマウント用）。 |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3080` | 許可するCORSオリジンのカンマ区切りホワイトリスト（`*` は禁止）。 |

---

## ストレージ構成

1.  **標準モード (put_archive)**:
    `RCE_DATA_DIR` が未設定の場合。Docker APIを介してファイルを転送します。特別なパーミッション設定なしで安全・確実に動作します。
2.  **ボリュームマウントモード**:
    `RCE_DATA_DIR` にホストの絶対パスを指定した場合。高速なファイルアクセスとホスト側へのデータ永続化が可能です。
    *注意: ホスト側のディレクトリは UID 1000 に書き込み権限が必要です。*

---

## 開発とテスト

本プロジェクトはテスト駆動開発 (TDD) に基づいて構築されており、**全 311 件のテストスイート** を備えています。

テストは以下のコマンドで一括実行してください。

```bash
# すべてのテストを一括で実行
LIBRECHAT_CODE_API_KEY=test-secret-key uv run pytest tests/ -v
```

> **注意**: テスト実行時には、ダミーの API キーを指定する `LIBRECHAT_CODE_API_KEY` 環境変数を付与して実行してください。指定がない場合、FastAPI の起動処理でエラーとなりテストが開始されません。

テスト範囲:
- API認証およびタイミング攻撃防御・エンドポイントの整合性
- 多言語実行 (Python/Bash/R) および AST による末尾式自動出力
- 画像（PNG/JPEG/SVG/WebP）、PDF、Office 文書、ZIP、CSV/Parquet 等のファイル処理
- パストラバーサル・二重拡張子・CRLF インジェクション等のセキュリティ検証
- 高負荷並列セッション管理、レースコンディション防御、リソース復旧とTTLクリーンアップ

---

## トラブルシューティング（LibreChat 連携エラー・構成調整）

LibreChat との連携時に問題が発生した場合は、以下の手順に従って構成を調整してください。

### 1. `401 Unauthorized (Invalid API Key)` エラーが発生する場合
APIサーバー側のログで `Received key: None, Expected key: your_secret_key` という警告が出ている場合、LibreChat側からAPIキーのヘッダー送信が欠落しています。

**【対処法】**:
LibreChat `v0.8.6` やそれ以降のバージョンであっても、一部のツール実行処理で `x-api-key` ヘッダーの送信が漏れる既知の不具合が発生する場合があります。
この問題が発生した場合は、APIキー認証を無効化（スキップ）しつつ、APIサーバーのポート露出をホストマシンのループバック（`127.0.0.1`）のみに制限することで安全に回避可能です。

1. **ポートの外部露出制限**:
   `docker-compose.yml` で APIサーバーのポート設定をホスト側の `127.0.0.1` にバインドするように設定します（デフォルトで制限されています）：
   ```yaml
   ports:
     - "127.0.0.1:8000:8000"
   ```
   これにより、APIキー認証が無効化された状態であっても、外部ネットワークからAPIサーバーへ直接アクセスされるのを防ぎます。なお、LibreChatコンテナとAPIサーバーコンテナ間の通信はDockerの内部ネットワーク（`librechat-network`）を介して直接行われるため、この制限下でも連携機能は正常に動作します。

2. **APIキー認証の無効化**:
   `.env` ファイルに以下の設定を追記してください：
   ```env
   DISABLE_CODE_API_AUTH=true
   ```

設定後、コンテナを再ビルド・再起動して変更を反映します：
```bash
docker compose -f docker-compose.yml -f docker-compose.librechat.yml build --no-cache code-interpreter-api
docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d --force-recreate
```

### 2. 外部からポート接続ができない場合（3000番ポートへの変更）
外部PCやネットワーク内の他の端末から LibreChat にアクセスできない場合、デフォルトの `3080` ポートではなく、ポート **`3000`** で待ち受けるようマッピングを変更します。
* `docker-compose.librechat.yml` 内の `librechat` サービスポートマッピング：
  ```yaml
  ports:
    - "3000:3080" # ホスト側の3000ポートをコンテナの3080ポートへ
  ```
* 変更後、コンテナを再起動してください。
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
  ```

### 3. Ollama モデルが UI の選択メニューに反映されない場合
`librechat.yaml` で `endpoints.ollama` を直接定義すると、Zod バリデーションエラー（構文エラー）が発生し、設定全体の読み込みが壊れる原因になります。また、Ollama が別プロジェクトの Docker ネットワークで動いている場合、ホスト名 `ollama` では名前解決できません。

**【対処法】**:
Ollama は標準で OpenAI 互換の API エンドポイントを提供しているため、`librechat.yaml` の `endpoints.custom`（OpenAI互換リスト）に統合するのが最も確実です。
1. **`librechat.yaml` の修正**:
   ```yaml
   endpoints:
     custom:
       - name: "Ollama"
         apiKey: "ollama"
         baseURL: "${OLLAMA_BASE_URL}/v1"
         models:
           default: ["qwen3.5:4b"]
           fetch: true
         titleConvo: true
         summarize: true
         modelDisplayLabel: "Ollama"
   ```
2. **`.env` ファイルで `host.docker.internal` 経由での接続に設定**:
   別プロジェクトで動く Ollama へホストマシン経由で接続させるため、以下を設定します。
   ```env
   OLLAMA_BASE_URL=http://host.docker.internal:11434
   ```
3. **コンテナ内からホスト側への名前解決（`extra_hosts`）を追加**:
   `docker-compose.librechat.yml` の `librechat` サービスに以下を追記してください。
   ```yaml
   extra_hosts:
     - "host.docker.internal:host-gateway"
   ```
* 変更後、コンテナを再起動してください。
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
  ```

---

## ドキュメント一覧 (OKF Knowledge Base)

システムの詳細仕様、設計原則、インフラ構築手順については `docs/` 配下のナレッジベースを参照してください。

* **[ナレッジインデックス (docs/README.md)](./docs/README.md)**: ドキュメント全体の目次
* **[システム全体アーキテクチャ (docs/architecture/overview.md)](./docs/architecture/overview.md)**: 全体システム構成とコンテナ実行フロー
* **[セキュリティモデル & 多層防御 (docs/architecture/security.md)](./docs/architecture/security.md)**: Socket Proxy、非ルート実行、HTTPヘッダー、コード注入防御
* **[並行制御とキャパシティ管理 (docs/architecture/concurrency.md)](./docs/architecture/concurrency.md)**: `WeakrefRLock` と `pending_sessions` によるレースコンディション防御
* **[多言語コード実行 & グラフ画像描画 (docs/domain/code-execution.md)](./docs/domain/code-execution.md)**: AST 解析、Matplotlib 日本語描画、Base64 画像自動キャプチャ
* **[セッションID解決仕様 & 自動フォールバック (docs/domain/session-resolution.md)](./docs/domain/session-resolution.md)**: LibreChat セッションID欠落に対する自動解決仕様
* **[ファイル処理 & UTF-8 仕様 (docs/domain/file-handling.md)](./docs/domain/file-handling.md)**: $O(N)$ ファイルマッピング、深いサブディレクトリ走査、RFC 5987 日本語ファイル名
* **[Docker構成 & ストレージモード (docs/infrastructure/docker-setup.md)](./docs/infrastructure/docker-setup.md)**: フルスタック/単体起動手順とストレージ選定
* **[サンドボックス環境設計 (docs/infrastructure/sandbox-image.md)](./docs/infrastructure/sandbox-image.md)**: CPU/GPU 版イメージ設計と日本語フォント構成
* **[リバースプロキシ & SSL設計 (docs/infrastructure/reverse-proxy.md)](./docs/infrastructure/reverse-proxy.md)**: Nginx SSL終端、SAN証明書、Artifacts (Sandpack Bundler) 連携
* **[設定リファレンス (docs/infrastructure/configuration.md)](./docs/infrastructure/configuration.md)**: 環境変数および `librechat.yaml` 設定一覧




