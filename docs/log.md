# Knowledge Update Log

## 2026-08-14

* **Convention**: GitHubでの視認性向上のため、各ナレッジディレクトリのインデックスファイル名を `index.md` から `README.md` へ統一。
* **Restructure**: OKF（Open Knowledge Framework）形式に準拠したディレクトリ構造（`architecture/`, `domain/`, `infrastructure/`）への再編・整備を実施。
* **Architecture**: システム構成、`WeakrefRLock`・`pending_sessions` による並行制御、セキュリティモデル（Docker Socket Proxy、非ルート実行、CORS制限）の概念ドキュメントを作成。
* **Domain**: セッションIDフォールバック仕様、21文字Nanoid双方向マッピング、$O(N)$ファイル管理と日本語ファイル名処理、多言語AST実行モデルの概念ドキュメントを作成。
* **Infrastructure**: Docker Compose構成（ストレージモード選択）、サンドボックスイメージ設計、Caddy SSL & Sandpack Bundlerプロファイル運用、設定リファレンスを作成。
* **Archive**: 過去の検証レポートおよび旧ガイドを `docs/archive/` に整理。

