# CI / 検証コマンド手順

## ローカル検証手順 (AI実行用)

開発および検証フェーズにおいて、以下のコマンドを順番に実行して整合性を担保すること。

### 1. パッケージ同期
```bash
uv sync
```

### 2. RCEカーネル（サンドボックスイメージ）のビルド
```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
```

### 3. テストスイートの実行 (pytest)
必ず以下の環境変数を定義した上で、一括で実行すること。
```bash
LIBRECHAT_CODE_API_KEY=test-secret-key uv run pytest tests/ -v
```

### 4. 静的コード解析 (Ruff)
```bash
uv run ruff check . --fix
```

### 5. セキュリティスキャン (Bandit)
```bash
uv run bandit -r . -x ./tests,./.venv
```

## Pull Request Checks

以下を必須チェックとする。

- ruff check
- ruff format --check
- pytest
- uv audit
- gitleaks detect

## Merge Requirement

すべての CI が成功した場合のみ merge 可能。