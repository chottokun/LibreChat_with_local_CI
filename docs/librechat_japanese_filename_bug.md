# Bug Report: LibreChat 日本語ファイル名の文字化け

## 1. 概要

LibreChatのファイルアップロード処理において、非ASCII文字（日本語、中国語等）を含むファイル名がアンダースコア（`_`）に置換される問題が存在する。

- **上流Issue**: [danny-avila/LibreChat#8792](https://github.com/danny-avila/LibreChat/issues/8792)
- **報告日**: 2025-08-01
- **ステータス**: 未修正（2026-02-26時点）
- **影響バージョン**: v0.7.9以降（v0.8.2でも未修正）

## 2. 症状

| 操作 | 結果 |
|---|---|
| ブラウザからファイル送信 | `テスト.txt` → 正しいUTF-8エンコードで送信される |
| LibreChat Node.js バックエンド受信 | ファイル名が `___.txt` に変換される |
| code-interpreter-api 受信 | 変換後の `___.txt` しか届かない |
| ファイルマネージャー表示 | DBにUTF-8名が保存されているため正しく表示される場合がある |

### 追加リスク

同じバイト長の日本語ファイル名が同一の `___...` パターンに変換されるため、ファイルの上書きが発生する可能性がある。

例:
- `販売データ_今週.pdf` → `__________.pdf`
- `販売データ_先週.pdf` → `__________.pdf` （上書き）

## 3. 原因

LibreChatの Node.js バックエンド（`/api/files` エンドポイント）において、`multer` 等のファイルアップロードミドルウェアが非ASCII文字をアンダースコアに置換するサニタイズ処理を行っている。

### データフロー

```
ブラウザ (テスト.txt) → POST /api/files → LibreChat Node.js (サニタイズ → ___.txt) → POST /upload → code-interpreter-api (___.txt を受信)
```

## 4. 本プロジェクトでの対応状況

### 対応済み（PR #64）

code-interpreter-api 側は日本語ファイル名を正しく処理できるように対応済み:

- **Dockerfiles**: UTF-8ロケール設定（`LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `PYTHONUTF8=1`）
- **main.py `list_files`**: `ls -1` → `python3 os.listdir` に変更（ロケール依存のエスケープ回避）
- **main.py `download_session_file`**: RFC 5987準拠の `Content-Disposition` ヘッダー生成
- **セキュリティ修正**: HTTPヘッダーインジェクション対策

### 未対応（LibreChat上流の修正が必要）

- LibreChat Node.js バックエンドのファイル名サニタイズロジック
- 修正箇所の候補: LibreChatの `api/server/services/Files/` 配下

## 5. 検証コマンド

```bash
# API直接テスト（日本語ファイル名が正しく処理されることを確認）
curl -X POST http://localhost:8000/upload \
  -H "X-API-Key: your_secret_key" \
  -F "entity_id=test-session" \
  -F "files=@テスト.txt;filename=テスト.txt"

# ファイル一覧確認
curl http://localhost:8000/files/test-session \
  -H "X-API-Key: your_secret_key"

# ダウンロードヘッダー確認（filename* にUTF-8エンコード名が含まれること）
curl -v "http://localhost:8000/download?session_id=test-session&filename=<file_id>&api_key=your_secret_key" 2>&1 | grep Content-Disposition
```

## 6. 将来の修正方針

LibreChat上流で Issue #8792 が修正された場合、以下の手順で検証する:

1. LibreChatのDockerイメージを最新版に更新
2. 日本語ファイル名のアップロードをUI経由で実行
3. code-interpreter-api のログで受信ファイル名を確認
4. ダウンロード時のファイル名が正しいことを確認

code-interpreter-api 側は既に対応済みのため、追加修正は不要のはず。
