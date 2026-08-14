# LibreChat Artifacts マルチ環境導入テスト検証報告書（作業進捗記録）

本ドキュメントは、LibreChat Artifacts機能（Sandpack Bundler）のマルチ環境運用設計におけるテスト実行の進捗および網羅的な検証結果を記録するものです。作業が途中で中断しても、現在のステータスが常に明確になるように段階的に更新されます。

---

## 1. 検証ステータス概要

| フェーズ | 検証内容 | ステータス | 最終実行日時 | 備考 |
| :--- | :--- | :--- | :--- | :--- |
| **フェーズ1** | 非SSL環境での Bundler 完全休止の検証 | **[PASS]** | 2026-06-06 10:27 | ユニットテスト正常通過 |
| **フェーズ2** | 自己署名SSL環境（Caddy）の構成検証 | **[PASS]** | 2026-06-06 10:27 | ユニットテスト正常通過 |
| **フェーズ3** | オンプレミスCAカスタム証明書適用の検証 | **[PASS]** | 2026-06-06 10:27 | ユニットテスト正常通過 |
| **網羅的検証** | Docker Compose 実構成のプロファイル統合テスト | **[PASS]** | 2026-06-06 10:27 | docker compose config による実機挙動テストの通過 |
| **回帰テスト** | 既存チャット/コード実行APIの全テスト検証 | **[PASS]** | 2026-06-06 10:27 | 全164件の既存テストに影響なし（LibreChat v0.8.6 確認済み） |

---

## 2. 網羅的テスト項目一覧と検証設計

現在、テストの信頼性をさらに高めるため、以下の網羅的テストの設計と追加実装を進めています。

### テスト区分 A: 静的ファイル構成検証（ユニットテスト）
- [x] **A-1**: `docker-compose.librechat.yml` に `sandpack-bundler` サービスが定義されていること。
- [x] **A-2**: `sandpack-bundler` サービスに `ssl-mode` プロファイルが定義されていること.
- [x] **A-3**: `.env.librechat` にフェーズ1、2および3の説明文が存在し、かつデフォルトで `SANDPACK_BUNDLER_URL` が空であること。
- [x] **A-4**: `Caddyfile` が存在し、 `your-domain.local:443` および `your-domain.local:8443` に対する `tls` 設定があること。
- [x] **A-5**: `docker-compose.librechat.yml` に `caddy` サービスが定義され、 `ssl-mode` プロファイル、ポート（443, 8443）、ボリュームが設定されていること。
- [x] **A-6**: `docker-compose.librechat.yml` の `volumes` 定義に `caddy-data` および `caddy-config` が定義されていること。
- [x] **A-7**: `Caddyfile` でカスタム証明書環境変数 `CUSTOM_CERT_PATH` / `CUSTOM_KEY_PATH` の参照によるハイブリッドTLSが設定されていること。
- [x] **A-8**: `docker-compose.librechat.yml` の `caddy` サービスに証明書フォルダ（`./certs:/certs:ro`）がマウントされ、環境変数定義が含まれていること。

### テスト区分 B: Docker Compose 挙動シミュレーション（統合テスト）
- [x] **B-1 (プロファイルなし起動シミュレーション)**:
  - `docker compose config` をプロファイルなしで実行したとき、 `sandpack-bundler` および `caddy` サービスが**含まれない（休止状態である）**ことを検証。
- [x] **B-2 (プロファイルあり起動シミュレーション)**:
  - `docker compose --profile ssl-mode config` を実行したとき、 `sandpack-bundler` および `caddy` サービスが**正しく構成に含まれる（起動状態である）**ことを検証。
- [x] **B-3 (YAML構文の妥当性検証)**:
  - `docker compose config` 自体がエラー（シンタックスエラーなど）にならず、正常終了することを検証。

---

## 3. 現在の実行ログと作業の進捗状況

### [2026-06-06 10:27] LibreChat v0.8.6 対応・全テスト実行（2段階）
- 認証テスト: `LIBRECHAT_CODE_API_KEY=test-dev-key uv run pytest tests/test_auth_unit.py tests/test_api.py -v` : **PASS** (14 tests)
- 全テスト（認証無効）: `LIBRECHAT_CODE_API_KEY=test-dev-key DISABLE_CODE_API_AUTH=true uv run pytest tests/ --ignore=tests/test_auth_unit.py -v` : **PASS** (150 tests)
- **合計: 164 tests PASSED, 0 FAILED**

### [2026-05-31 09:45-09:46] 静的ユニットテスト & 既存テスト実行
- `pytest tests/test_artifacts_phase1.py` : **PASS** (2 tests)
- `pytest tests/test_artifacts_phase2.py` : **PASS** (3 tests)

### [2026-05-31 11:22] オンプレミス（フェーズ3）ユニットテストの追加と実行
- `pytest tests/test_artifacts_onprem.py` : **PASS** (3 tests)

### [2026-05-31 09:48] 統合テスト (区分 B) の実行と全テスト回帰検証
- `pytest tests/test_artifacts_integration.py` : **PASS** (3 tests)

---

## 4. 作業中断・再開ガイド

本プロジェクトでのテスト実行または開発が中断された場合、以下のコマンドを実行することでいつでも状態を再検証できます：

```bash
# ステップ1: 認証テスト（APIキーを有効にした状態で実行）
LIBRECHAT_CODE_API_KEY=test-dev-key uv run pytest tests/test_auth_unit.py tests/test_api.py -v

# ステップ2: その他全テスト（認証を無効にした状態で実行）
LIBRECHAT_CODE_API_KEY=test-dev-key DISABLE_CODE_API_AUTH=true uv run pytest tests/ --ignore=tests/test_auth_unit.py -v
```
上記の全テストが PASS すれば、LibreChat v0.8.6 との連携を含めたオンプレミス本番環境の構築（フェーズ3）に対応できる状態が保証されています。
