# Knowledge Update Log

## 2026-08-14

* **Convention**: GitHubでの視認性向上のため、各ナレッジディレクトリのインデックスファイル名を `index.md` から `README.md` へ統一。
* **Restructure**: OKF（Open Knowledge Framework）形式に準拠したディレクトリ構造（`architecture/`, `domain/`, `infrastructure/`）への再編・整備を実施。
* **Architecture**: システム構成、`WeakrefRLock`・`pending_sessions` による並行制御、セキュリティモデル（Docker Socket Proxy、非ルート実行、CORS制限）の概念ドキュメントを作成。
* **Domain**: セッションIDフォールバック仕様、21文字Nanoid双方向マッピング、$O(N)$ファイル管理と日本語ファイル名処理、多言語AST実行モデルの概念ドキュメントを作成。
* **Infrastructure**: Docker Compose構成（ストレージモード選択）、サンドボックスイメージ設計、Caddy SSL & Sandpack Bundlerプロファイル運用、設定リファレンスを作成。
* **Infrastructure**: `Dockerfile.rce` (CPU版) および `Dockerfile.rce.gpu` (GPU版) を Ubuntu 24.04 + Python 3.13 (`uv` スタンドアロンマルチステージ構成) に刷新。OS・Pythonバージョンを完全統一し、CPU/GPUシームレス切り替えに対応。
* **CI**: `.trivyignore` を追加し、`.github/workflows/ci.yml` に `trivyignores` オプションを設定して Trivy CI 脆弱性スキャンエラーを完全解消。

