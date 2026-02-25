# LibreChat Custom Code Interpreter API

LibreChat向けの安全なサンドボックス型Code Interpreter APIです。隔離されたDockerコンテナ内でPythonコードを実行することができます。これにより、LLMがLibreChatのUI上で直接コードを実行し、データを生成し、ファイルを作成することが可能になります。

Google Geminiなどのクラウドプロバイダーはもちろん、Ollamaなどのローカルモデルを使用した完全オフライン環境でのAIコード実行にも対応しています。

## 🚀 特徴 (Features)

- **サンドボックス実行**: Pythonコードは、メモリとCPUの制限が設定可能な隔離されたDockerコンテナ（`custom-rce-kernel`）内で実行されます。デフォルトではネットワークアクセスは遮断されています。
- **LibreChat ネイティブ統合**: LibreChatのCode Interpreter API仕様（`/exec`, `/upload`, `/download`, `/files`）に完全準拠。生成されたファイルはチャット画面内にネイティブな添付ファイルとして表示されます。
- **セッションの永続化**: セッションごとにファイルシステムの状態を保持します。アップロードしたファイルや生成されたデータは、複数回のメッセージのやり取りを跨いでも安全に保持されます。
- **カスタマイズ可能な環境**: 専用のDockerイメージにより、`pandas`, `matplotlib`, `numpy` などの科学技術計算ライブラリがプリインストールされています。
- **オフライン・ローカルAI対応**: `qwen2.5-coder:3b` のようなローカルのOllamaモデルと完全に連携し、完全なオフライン稼働が可能です。
- **GPUアクセラレーション**: CUDA対応のサンドボックスイメージを使用することで、GPUによる高速なコード実行をサポートします。
- **セキュアな設計**: APIキー認証とDocker Socket Proxyによって保護されたアーキテクチャを採用しています。
- **環境変数による一括設定**: リソース制限やシステムの挙動はすべて `.env` 変数で制御可能です。

## 📋 必須要件 (Prerequisites)

- **Docker**: インストールされ、起動していること。
- **Python 3.13+**: ローカル開発時のみ（Docker Composeでデプロイする場合は不要です）。
- **uv**: Pythonパッケージ管理ツールとして推奨。

---

## ⚡ クイックスタート: LibreChatフルスタック構成

LibreChat本体、Code Interpreter API、そしてDBをすべてまとめて起動する推奨セットアップです。

### 1. 環境変数の設定

テンプレートをコピーして環境変数ファイルを作成します：

```bash
cp .env.librechat .env
```

`.env` 内の以下の **「変更必須項目」** を必ず更新してください（セキュリティのために重要です）：
- **`JWT_SECRET` / `JWT_REFRESH_SECRET`**: JWT 認証用シークレット。
- **`CREDS_KEY` / `CREDS_IV`**: 認証情報の暗号化キー。
- **`LIBRECHAT_CODE_API_KEY`**: この API と LibreChat が通信するための共有キー。

### 2. サンドボックスイメージのビルド

APIがPython実行環境を生成するために使うベースイメージをビルドします：

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
```

### 3. フルスタックの起動

MongoDB、Meilisearch、Code Interpreter API、LibreChatを一括で立ち上げます：

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d
```

LibreChatは **http://localhost:3080** で利用可能になります。

### 4. ローカルモデルの接続 (オプション: Ollama)

Ollamaを別のDockerコンテナとして稼働させており、LibreChatと連携させたい場合：

```bash
docker network connect librechat-network ollama
```
*(`.env` の `OLLAMA_BASE_URL` が正しく設定されていることを確認してください)*

---

## 🛠️ セットアップ: Code Interpreter API 単体のみ

すでに別の場所でLibreChatを稼働させている場合は、API単体で立ち上げることができます。

### Docker Compose を使用 (推奨)

```bash
# まずサンドボックスイメージをビルドします
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .

# APIとDocker Socket Proxyを起動します
docker compose up -d --build
```

**既存のLibreChat側の設定:**
LibreChatの `.env` に以下を追加して、このAPIに向くように設定してください：
```dotenv
LIBRECHAT_CODE_BASEURL=http://<あなたのAPIホスト>:8000
LIBRECHAT_CODE_API_KEY=your_secret_key
```

### ローカル開発 (Docker Composeを使わない場合)

```bash
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🏎️ GPU サポート

サンドボックス内でCUDAを利用した実行を行いたい場合：

```bash
# GPU対応のサンドボックスイメージをビルド
docker build -f Dockerfile.rce.gpu -t custom-rce-kernel:gpu .

# GPUサポートを有効にして起動
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## ⚙️ 設定フラグ (Configuration)

すべての設定は `.env` ファイル内の環境変数で制御されます：

| 変数名 | デフォルト値 | 説明 |
|---|---|---|
| `LIBRECHAT_CODE_API_KEY` | `your_secret_key` | 認証用のAPIキー |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | サンドボックスとして起動するDockerイメージ名 |
| `RCE_MEM_LIMIT` | `512m` | サンドボックスコンテナ1つあたりのメモリ制限 |
| `RCE_CPU_LIMIT` | `500000000` | CPUクオータ (ナノ秒)。デフォルトは0.5 CPU |
| `RCE_MAX_SESSIONS` | `100` | 同時に起動できるサンドボックスコンテナの最大数 |
| `RCE_NETWORK_ENABLED` | `false` | サンドボックス内からの外部インターネットアクセスを許可するか |
| `RCE_GPU_ENABLED` | `false` | サンドボックスへのGPUパススルーを有効にするか |
| `RCE_DATA_DIR` | (なし) | ホスト側のデータ保存用ディレクトリ（これと `./sessions` のマウントが必要、詳細は下記） |

### 📁 ファイル保存と永続化 (Storage & Persistence)

本 API には、ファイルの保存方法として 2 つのモードがあります。

#### 1. 標準モード (Default: `put_archive`)
`.env` の `RCE_DATA_DIR` を設定しない（またはコメントアウトする）場合のデフォルト動作です。
- **メリット**: 追加設定なしで、パーミッション問題を気にせず「すぐに」動きます。
- **デメリット**: 大規模なファイルの扱いは、ボリューム方式に比べてわずかに低速です。
- **仕組み**: Docker API を通じてファイルを直接転送します。

#### 2. 高速・永続化モード (Advanced: Volume Mounting)
ホスト側のディレクトリをマウントして使用します。大規模なデータ分析や、コンテナが消えてもファイルをホストに残したい場合に推奨されます。

**設定手順:**
1. **ディレクトリの作成**: ホスト側に保存用ディレクトリを作成します。
   ```bash
   mkdir -p sessions
   ```
2. **権限の付与**: API コンテナのユーザー (UID 1000) が書き込めるように権限を設定します。 **※Linux環境では必須の手順です。**
   ```bash
   sudo chown -R 1000:1000 sessions
   ```
3. **環境変数の設定**: `.env` で **絶対パス** を指定します。
   ```dotenv
   RCE_DATA_DIR=/home/user/Project/sessions
   ```
4. **再起動**: `docker compose up -d` で反映されます。

> [!TIP]
> もしボリュームモード設定時にパスが間違っていたり権限がなかったりしても、API は自動的に「標準モード」にフォールバックして動作を継続するため、チャットが途切れることはありません。

---

## 🏗️ アーキテクチャ図

```text
LibreChat (port 3080)
    │
    ├── MongoDB (セッション/履歴保存)
    ├── Meilisearch (検索エンジン)
    └── Code Interpreter API (port 8000)
            │
            ├── Docker Socket Proxy (セキュリティレイヤー)
            └── RCE Sandbox Containers (隔離されたPython実行環境群)
```

---

## 🐛 トラブルシューティング

よくある問題については、`docs/` フォルダ内にある詳細な **[LibreChat Integration Guide](docs/librechat_integration_guide.md)** を参照してください。以下の解決策が記載されています：
- ファイルダウンロード時の "Network Error" (通信エラー)。
- `400 Bad Request` や LibreChat の ID 検証エラー。
- Nginx リバースプロキシのルーティングの誤解。
- ブラウザ固有のフロントエンドのバグ (Blob URL周り)。

---

## 🧪 テストの実行

```bash
uv run pytest tests/ -v
```

テストスイートは以下の範囲をカバーしています：
- API認証とエンドポイントのスキーマ
- Kernel Manager のセッション作成とライフサイクル
- 障害発生時のコンテナ復旧とオーファン（迷子）クリーンアップ
- Docker Socket のセキュリティプロキシの検証
