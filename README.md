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
    docker compose -f docker-compose.yml -f docker-compose.full.yml up -d
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
