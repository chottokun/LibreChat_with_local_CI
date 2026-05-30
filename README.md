# LibreChat Code Interpreter API (Custom RCE)

LibreChatにコード実行機能を提供する、サンドボックス型のCode Interpreter APIです。隔離されたDockerコンテナ群をセッションごとに動的に管理し、安全にコードを実行するためのバックエンドを提供します。

## 概要

本APIは、LibreChatのCode Interpreter仕様に準拠したエンドポイント（`/exec`, `/upload`, `/download`, `/files`）を提供します。隔離環境として専用のDockerイメージを使用し、リソース制限やネットワーク遮断を施した状態でユーザーのコードを実行します。

クラウドプロバイダー（Gemini, OpenAI等）のAPI、およびローカルLLM（Ollama等）のいずれの構成でも利用可能です。

## 主要な機能と仕様

- **多言語対応**: Pythonに加え、BashおよびR言語の実行に対応しています。
- **サンドボックス隔離**: 各セッションはメモリとCPU制限が課された独立したDockerコンテナ内で実行されます。
- **セッション永続性**: メッセージ間でのファイルシステムの状態を維持します。
- **セキュリティ**:
  - `LIBRECHAT_CODE_API_KEY` による認証の強制。
  - Docker Socket Proxyを介したDocker APIへの安全なアクセス。
  - アップロード/ダウンロード時のディレクトリトラバーサル脆弱性対策を実装済み。
- **効率的なマッピング**: セッションごとのファイルID管理を $O(N)$ で処理するスケーラブルな設計。
- **GPUサポート**: CUDA対応イメージを用いたGPU計算をサポート（オプション）。

## 必須要件

- **Docker**: エンジンが稼働していること。
- **Python 3.13+**: API本体の実行に必要（ローカル開発時のみ）。
- **uv**: パッケージおよび仮想環境管理（推奨）。

---

## セットアップ手順

### A. フルスタック構成 (LibreChat + API + DB)

1.  **環境変数の設定**:
    ```bash
    cp .env.librechat .env
    ```
    `.env` 内の `JWT_SECRET`, `CREDS_KEY`, `LIBRECHAT_CODE_API_KEY` を必ず一意の値に更新してください。

2.  **実行イメージの準備**:
    ```bash
    docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
    ```

3.  **起動**:
    ```bash
    docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d
    ```

### B. API単体での起動 (既存のLibreChatと連携)

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
docker compose up -d --build
```
LibreChat側の `.env` で `LIBRECHAT_CODE_BASEURL` と `LIBRECHAT_CODE_API_KEY` を設定してください。

---

## 環境変数 (Configuration)

| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `LIBRECHAT_CODE_API_KEY` | (必須) | APIアクセス認証用の共有キー。 |
| `DISABLE_CODE_API_AUTH` | `false` | `true` に設定するとAPIキーの認証を一時的に無効化（スキップ）します。テスト環境や一部のバグ回避用。 |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | サンドボックスコンテナに使用するイメージ。 |
| `RCE_MEM_LIMIT` | `512m` | コンテナあたりのメモリ上限。 |
| `RCE_CPU_LIMIT` | `500000000` | コンテナあたりのCPU制限 (0.5 CPU)。 |
| `RCE_MAX_SESSIONS` | `100` | 最大同時セッション数。 |
| `RCE_NETWORK_ENABLED` | `false` | サンドボックス内からの外部通信許可。 |
| `RCE_DATA_DIR` | (なし) | ホスト側のデータ保存先パス（ボリュームマウント用）。 |

---

## ストレージ構成

1.  **標準モード (put_archive)**:
    `RCE_DATA_DIR` が未設定の場合。Docker APIを介してファイルを転送します。特別なパーミッション設定なしで動作します。
2.  **ボリュームマウントモード**:
    `RCE_DATA_DIR` にホストの絶対パスを指定した場合。高速なファイルアクセスとホスト側へのデータ永続化が可能です。
    *注意: ホスト側のディレクトリは UID 1000 に書き込み権限が必要です。*

---

## 開発とテスト

本プロジェクトはテスト駆動開発 (TDD) に基づいて構築されており、100項目以上のテストスイートを備えています。

```bash
# テストの実行
uv run pytest tests/
```

テスト範囲:
- API認証およびエンドポイントの整合性
- 多言語実行 (Python/Bash/R) の正常系・異常系
- ディレクトリトラバーサル等のセキュリティ検証
- 高負荷時の並列セッション管理とリソース復旧

---

## トラブルシューティング（LibreChat 連携エラー）

LibreChat との連携時に問題が発生した場合は、以下の手順に従って解決してください。

### 1. `401 Unauthorized (Invalid API Key)` エラーが発生する場合
一部の LibreChat バージョン（あるいは特定の実験的設定）には、**APIキーをリクエストヘッダーに正しく注入して送信しない（ヘッダーが欠落する）という既知のバグ**が存在します。
APIサーバー側のログで `Received key: None, Expected key: your_secret_key` という警告が出ている場合、このバグに該当します。

**【解決策】**:
`.env` ファイルに以下の設定を追記し、APIキー認証を一時的に無効化（スキップ）してください。ローカルネットワーク（Dockerブリッジ）内での連携であれば、安全に機能します。
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
`librechat.yaml` で `endpoints.ollama` を直接定義すると、Zod バリデーションエラー（構文エラー）が発生し、設定全体の読み込みが壊れる原因になります。
また、Ollama が別プロジェクトの Docker ネットワークで動いている場合、ホスト名 `ollama` では名前解決できません。

**【解決策】**:
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

### 4. 日本語ファイル名の完全サポート（文字化けバグの解決と仕組み）
かつての LibreChat 上流（および Node.js の `multer`/`busboy` ミドルウェア仕様）では、ブラウザから非ASCII文字（日本語等）を含むファイルをアップロードした際に、ファイル名が文字化け（Latin1誤解釈）したり、アンダースコア（`_`）に強制サニタイズされたりする課題が存在しました（Issue #8792）。

**現在の解決状況と仕組み**:
現在利用されている LibreChat のバージョン（v0.8.4以降のファイルシステム設計）においては、この問題が完全に回避され、**日本語ファイル名がコンテナ（RCE）内でも完全に維持されて動作する**ようになっています。この連携の背後には、以下の強固な設計が存在します。

1. **上流（LibreChat）のプロキシ転送の改善**:
   LibreChatは、ローカルディスク保存時の安全性を確保するためにファイルシステム上では一時的にサニライズされた名前を使用しますが、データベース（MongoDB）側には「ユーザーがアップロードしたオリジナルの日本語ファイル名」をUTF-8で保持しています。そして、当RCE APIの `/upload` エンドポイントへファイルを転送（プロキシ）する際、**データベースから引き出したオリジナルの日本語名（UTF-8）をマルチパートリクエストの filename パラメータに設定して送信する設計**になりました。
2. **本API側の受け入れ設計**:
   API（FastAPI）側の `UploadFile` は、この転送されてきた UTF-8 ファイル名をデコードして `f.filename` に正しく復元します。本APIはこれに無駄なサニタイズや強制置換をかけず、オリジナルの名前のままコンテナの作業用ボリューム（`/mnt/data`）に配置します。
3. **RCEコンテナ内のUTF-8ロケール**:
   `Dockerfile.rce` でロケール環境変数（`LANG=C.UTF-8`, `PYTHONUTF8=1`）を強制設定しているため、コンテナのOSおよびPythonランタイムが日本語ファイル名を正しく処理でき、ユーザープログラムからファイルエラーにならずに直接読み書き（例: `open('日本語ファイル名.txt')`）できます。
4. **ダウンロード時の RFC 5987 準拠**:
   RCEから結果ファイルをダウンロードする際、APIは RFC 5987 に完全準拠した `Content-Disposition: attachment; filename*=UTF-8''...` ヘッダーを生成して返却するため、ブラウザ側でも日本語ファイル名が文字化けせずに復元されます。


### 5. セッションID欠落によるコンテナの頻繁な再生成問題
ファイルを添付せずにコードを実行する際、LibreChatのクライアント側モジュール（`@librechat/agents`）がAPIリクエストのトップレベルで `session_id` を送信しないという仕様上の挙動があります。このため、リクエストごとに新しいコンテナが起動され、数秒の起動オーバーヘッドや状態（変数や作成されたファイル）の消失が発生する問題があります。

**本API（Custom RCE）側の自動フォールバック機能**:
本APIでは、この上流側の制限に対処するため、複数のフォールバック機構を内蔵しています（特別な設定変更は不要です）。
1. **`user_id` によるバインド**: リクエストに `user_id` が含まれている場合、自動的に `user_<user_id>` をセッションIDとしてバインドし、コンテナを再利用します。
2. **直前セッションの再利用**: 直前5分以内にファイルのアップロード成功実績があり、かつ実行リクエストで `session_id` が欠落している場合、直前のアップロードセッションIDを自動で再利用し、同一コンテナ内でコードを実行します。

これにより、コンテナの無駄な再生成が抑制され、起動レイテンシがミリ秒単位に低減し、セッション間の状態が安定して維持されます。

