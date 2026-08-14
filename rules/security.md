# Security Rules

## Dependency Audit

依存パッケージの脆弱性を定期的に確認する。

- Local check:
  ```bash
  uv audit
````

* CI check:
  Pull Request 時に自動実行する。

## Secrets

* API Key、Token、Password をコードへ直接記載しない
* `.env` を利用する
* Gitleaks による検査を通過すること

## Dependency Policy

* 新規依存は必要性を確認する
* 可能な限り標準ライブラリを優先する

## RCE Security Invariants (設計不変条件)

* **Docker Socket**: ホストの `/var/run/docker.sock` の直接マウントは厳禁。必ず `docker-socket-proxy` を中継し最小権限（`BUILD=0`, `VOLUMES=0` 等）とする。
* **CORS**: `CORS_ALLOWED_ORIGINS` にワイルドカード `*` を使用しない（明示的ホワイトリスト必須）。
* **Path Validation**: すべてのファイル名・セッションIDは `sanitize_id` / `Path.parts` / `is_relative_to` でトラバーサルを徹底防御する。
* **Container Isolation**: 非ルート実行（`sandboxuser: 1000`）、デフォルトのネットワーク遮断（`network_disabled: True`）を維持する。
* **Code Injection Defense**: コード実行はコマンドライン直接渡し（`-c`）ではなく、`tarfile`（`put_archive`）経由で一時ファイルとして安全に注入し、`finally` で自動削除する。


