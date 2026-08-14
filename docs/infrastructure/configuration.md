---
type: Concept
title: Configuration Reference
description: RCE API環境変数、LibreChat環境変数、librechat.yaml 設定リファレンス
status: stable
generated:
  by: agent/gemini-3.7-flash
  at: 2026-08-14T09:30:00+09:00
tags:
  - infrastructure
  - configuration
  - env
  - librechat-yaml
---

# Configuration Reference (設定リファレンス)

## 1. 概要

本ドキュメントは、LibreChat Custom RCE API および LibreChat 本体を構成するためのすべての環境変数と設定ファイルの完全なリファレンスです。

## 2. API サーバー環境変数 (`main.py`)

| 変数名 | デフォルト値 | 必須 | 説明 |
|---|---|---|---|
| `LIBRECHAT_CODE_API_KEY` | (なし) | ○ (認証有効時) | APIアクセス認証用の共有シークレットキー。 |
| `DISABLE_CODE_API_AUTH` | `false` | - | `true` に設定するとAPIキー認証をスキップ。テスト・ローカル環境用。 |
| `DOCKER_HOST` | (環境依存 / `tcp://docker-proxy:2375`) | - | Docker Socket Proxy またはホストデーモンの接続先。 |
| `RCE_DATA_DIR` / `RCE_DATA_DIR_HOST` | (なし) | - | ホスト側のセッション共有ディレクトリ絶対パス（ボリュームマウントモード用）。 |
| `RCE_DATA_DIR_INTERNAL` | `/app/shared_volumes/sessions` | - | APIコンテナ内部のセッションマウントパス。 |
| `RCE_IMAGE_NAME` | `custom-rce-kernel:latest` | - | サンドボックスコンテナに使用するDockerイメージ名。 |
| `RCE_GPU_ENABLED` | `false` | - | `true` に設定すると NVIDIA GPU アクセラレーションを有効化。 |
| `RCE_MEM_LIMIT` | `512m` | - | コンテナあたりの最大メモリ上限。 |
| `RCE_CPU_LIMIT` | `500000000` | - | コンテナあたりの最大CPUクォータ（500,000,000 = 0.5 CPU）。 |
| `RCE_MAX_SESSIONS` | `100` | - | システム全体の最大同時アクティブセッション数。 |
| `RCE_SESSION_TTL` | `3600` | - | セッションコンテナの生存時間（秒）。非アクティブ時に自動クリーンアップ。 |
| `RCE_NETWORK_ENABLED` | `false` | - | サンドボックス内の外部ネットワークアクセス許可フラグ（セキュリティ上 `false` 推奨）。 |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3080` | - | 許可するCORSオリジンのカンマ区切りリスト（`*` は禁止）。 |

## 3. LibreChat 側設定 (`.env.librechat` / `.env`)

```env
# RCE API 接続設定
LIBRECHAT_CODE_BASEURL=http://code-interpreter-api:8000
LIBRECHAT_CODE_API_KEY=your_secure_secret_key
CODE_API_KEY=your_secure_secret_key

# セキュリティシークレット
JWT_SECRET=your_jwt_secret
CREDS_KEY=your_creds_key

# LLMプロバイダー設定例 (Ollama)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## 4. `librechat.yaml` 設定例

```yaml
version: "1.1.5"
cache: true

# Code Interpreterの有効化
codeInterpreter:
  enabled: true

# カスタムエンドポイント設定 (Ollama連携)
endpoints:
  custom:
    - name: "Ollama"
      apiKey: "ollama"
      baseURL: "${OLLAMA_BASE_URL}/v1"
      models:
        default: ["qwen2.5-coder:3b"]
        fetch: true
      titleConvo: true
      summarize: true
      modelDisplayLabel: "Ollama Local"
```

## 5. 関連ドキュメント
* [Docker Setup & Storage Modes](./docker-setup.md) - 起動コマンドと構成
* [Security Model](../architecture/security.md) - セキュリティ設計
