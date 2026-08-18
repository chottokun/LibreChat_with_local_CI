# Knowledge Update Log

## 2026-08-18

* **Documentation**: [docs/infrastructure/docker-setup.md](./infrastructure/docker-setup.md) および [docs/infrastructure/reverse-proxy.md](./infrastructure/reverse-proxy.md) を更新。`--profile ssl-mode` による Nginx SSL/TLS リバースプロキシ起動手順、アクセスURL、HTTP/HTTPSリダイレクト仕様、および通常起動時のループバック（`127.0.0.1:3000`）セキュリティ制限の解説を体系的に追記。
* **Security & Architecture**: [docs/architecture/security.md](./architecture/security.md) および [docs/infrastructure/docker-setup.md](./infrastructure/docker-setup.md) に、ボリュームマウント時のセッション個別サブディレクトリマウントによるユーザー間隔離、コンテナサイズ実測値（ベース700MB / 差分数十KB〜数MB）、TTL（`RCE_SESSION_TTL`）長期保持の妥当性、およびTTL経過後のオンデマンド自動再生成ライフサイクルの詳細を体系化。

## 2026-08-14

* **Standardization**: OKF (Open Knowledge Format) v0.2 公式仕様に基づき、`docs/` 配下の全ドキュメント（17件）のフロントマターを完全整備。`status: stable` への統一、OKF Actor記法準拠の `generated: { by: agent/..., at: ... }` 付与、およびルート [docs/README.md](./README.md) の `okf_version: "0.2"` YAML構文修正を完了。
* **Documentation**: [README.md](../README.md) および [README_en.md](../README_en.md) を最新化。311件のテストスイート実績、グラフ自動インライン描画、tarfileコード注入防御、Nginx SSL/Artifacts連携、環境変数一覧、OKFナレッジリンクを体系的に更新。
* **Refinement**: `docs/` 配下の全ドキュメントを最新コードベースと突合検証。環境変数（`RCE_GPU_ENABLED`, `DOCKER_HOST`）の反映、`WeakrefRLock` 実装コードとの整合、Nanoid レスポンススキーマ（`images`, `storage_session_id` 等）の完全同期を完了。
* **Cleanup**: どこからも参照されていなかったテスト結果画像（`docs/assets/`）および過去の作業メモ（`docs/archive/`）を完全削除。
* **Security**: RCE 多層防御アーキテクチャ（HTTP セキュリティヘッダー、tarfile コード安全注入、Path Traversal サニタイズ詳細、Socket Proxy 最小権限化、DoS/セッション制御）を [docs/architecture/security.md](./architecture/security.md) に拡充・体系化。
* **Convention**: GitHubでの視認性向上のため、各ナレッジディレクトリのインデックスファイル名を `index.md` から `README.md` へ統一。
* **Restructure**: OKF（Open Knowledge Framework）形式に準拠したディレクトリ構造（`architecture/`, `domain/`, `infrastructure/`）への再編・整備を実施。
* **Architecture**: システム構成、`WeakrefRLock`・`pending_sessions` による並行制御、セキュリティモデル（Docker Socket Proxy、非ルート実行、CORS制限）の概念ドキュメントを作成。
* **Domain**: セッションIDフォールバック仕様、21文字Nanoid双方向マッピング、$O(N)$ファイル管理と日本語ファイル名処理、多言語AST実行モデルの概念ドキュメントを作成。
* **Infrastructure**: Docker Compose構成（ストレージモード選択）、サンドボックスイメージ設計、Caddy SSL & Sandpack Bundlerプロファイル運用、設定リファレンスを作成。
* **Infrastructure**: `Dockerfile.rce` (CPU版) および `Dockerfile.rce.gpu` (GPU版) を Ubuntu 24.04 + Python 3.13 (`uv` スタンドアロンマルチステージ構成) に刷新。OS・Pythonバージョンを完全統一し、CPU/GPUシームレス切り替えに対応。
* **CI**: `.trivyignore` を追加し、`.github/workflows/ci.yml` に `trivyignores` オプションを設定して Trivy CI 脆弱性スキャンエラーを完全解消。
* **Refactor**: `main.py` のファイルパス操作を `os.path` から `pathlib.Path`（`Path.resolve()`, `is_relative_to()`, `Path.name`）へ完全移行し、型安全性とパストラバーサル防御を強化。
* **Testing**: PDF, 画像 (PNG/JPEG/SVG/WebP), 音声/動画, オフィス文書 (Excel/Word), 圧縮ファイル (ZIP/GZIP), データ形式 (CSV/Parquet) の多種ファイル対応および二重拡張子・CRLFヘッダーインジェクション等の批判的（Adversarial）テストスイート（全311件パス）を追加。
* **Domain & UI**: RCE で生成されたグラフ画像（Matplotlib 等）の自動検知と Base64 エンコード機能を実装し、LibreChat チャット UI メッセージ内での即時インライン描画に対応。`files` メタデータ（`storage_session_id`, `session_id`, `inherited`）の整合性を確保。
* **Domain & Storage**: `/mnt/data/` 配下の深いサブディレクトリ（ネスト構造）のファイルを `os.walk` で再帰走査し、FastAPI の `{filename:path}` ワイルドカードルーティングおよび階層パスを保持した Nanoid 逆引き解決により、深いパスのファイル表示・ダウンロードに完全対応。
* **Domain & Artifacts**: AI が作成・保存したプログラムコードファイル（`.py`, `.sh`, `.R`, `.js`, `.ts` 等）の自動検知とダウンロード・プレビュー仕様を体系化。
* **Infrastructure & Security**: 正式な CA 証明書（Let's Encrypt / 社内プライベート PKI / 商用 CA）への無停止入れ替え手順、モジュラス検証、パーミッション仕様を [docs/infrastructure/reverse-proxy.md](./infrastructure/reverse-proxy.md) に体系化。


