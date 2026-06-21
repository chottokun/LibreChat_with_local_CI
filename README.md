# LibreChat Code Interpreter API (Custom RCE)

LibreChatにコード実行機能を提供する、サンドボックス型のCode Interpreter APIです。隔離されたDockerコンテナ群をセッションごとに動的に管理し、安全にコードを実行するためのバックエンドを提供します。

## 概要

本APIは、LibreChatのCode Interpreter仕様に準拠したエンドポイント（`/exec`, `/upload`, `/download`, `/files`）を提供します。隔離環境として専用のDockerイメージを使用し、リソース制限やネットワーク遮断を施した状態でユーザーのコードを実行します。

クラウドプロバイダー（Gemini, OpenAI等）のAPI、およびローカルLLM（Ollama等）のいずれの構成でも利用可能です。

## 主要な機能と仕様

- **多言語対応**: Pythonに加え、BashおよびR言語の実行に対応しています。
- **サンドボックス隔離**: 各セッションはメモリとCPU制限が課された独立したDockerコンテナ内で実行されます。
- **セッション永続性**: メッセージ間でのファイルシステムの状態を維持します。
- **堅牢な並行制御**: セッション個別ロック（`WeakrefRLock`）および起動中セッションの追跡（`pending_sessions`）により、最大容量制限時のレースコンディションを完全に防御。
- **セキュリティ**:
  - `LIBRECHAT_CODE_API_KEY` による認証の強制。
  - Docker Socket Proxyを介したDocker APIへの安全なアクセス。
  - アップロード/ダウンロード時のディレクトリトラバーサル脆弱性対策を実装済み。
  - CORSでのワイルドカード `'*'` 使用の拒否および明示的なホワイトリストの厳格な検証。
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

本プロジェクトはテスト駆動開発 (TDD) に基づいて構築されており、58ファイル276件以上のテストスイートを備えています。

テストは以下のコマンドで一括実行してください。

```bash
# すべてのテストを一括で実行
LIBRECHAT_CODE_API_KEY=test-secret-key uv run pytest tests/ -v
```

> **注意**: テスト実行時には、ダミーの API キーを指定する `LIBRECHAT_CODE_API_KEY` 環境変数を付与して実行してください。指定がない場合、FastAPI の起動処理でエラーとなりテストが開始されません。

テスト範囲:
- API認証およびエンドポイントの整合性
- 多言語実行 (Python/Bash/R) の正常系・異常系
- ディレクトリトラバーサル等のセキュリティ検証
- 高負荷時の並列セッション管理とリソース復旧

---

## トラブルシューティング（LibreChat 連携エラー・構成調整）

LibreChat との連携時に問題が発生した場合は、以下の手順に従って構成を調整してください。

### 1. `401 Unauthorized (Invalid API Key)` エラーが発生する場合
APIサーバー側のログで `Received key: None, Expected key: your_secret_key` という警告が出ている場合、LibreChat側からAPIキーのヘッダー送信が欠落しています。

**【対処法】**:
LibreChat `v0.8.6` 以降ではこの問題は修正済みです。本認証済みバージョンを使用してください。
万が一不具合が発生する場合は、APIキー認証を一時的に無効化（スキップ）することで回避可能です。`.env` ファイルに以下の設定を追記してください（Dockerブリッジ等、ローカルネットワーク内であれば安全に機能します）。
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

### 4. システム内部仕様および各種バグ解決リファレンス
文字コードの処理仕様やセッションID欠落に対するAPIの自動防衛機構など、本システム固有の技術的仕様については、将来の開発継続および機能追加の参考として以下の専用設計書を参照してください。

* **[日本語ファイル名の処理仕様と設計リファレンス](./docs/librechat_japanese_filename_bug.md)**: 
  LibreChatからプロキシされるUTF-8オリジナルファイル名の中継仕様、およびコンテナ内でのUTF-8ロケール（Matplotlib等）による文字化け回避設計の技術仕様。
* **[セッションID解決仕様と自動フォールバック設計リファレンス](./docs/librechat_session_id_bug_analysis.md)**:
  上流ツールからのセッションID欠落挙動に対し、本API側で自動的に行う「`user_id` によるバインド」「直前5分間セッション再利用キャッシュ」による状態維持とミリ秒起動を実現しているフォールバック設計仕様。


