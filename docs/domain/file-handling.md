---
type: Concept
title: File Handling & UTF-8
description: O(N)ファイル管理、日本語UTF-8ファイル名処理、Content-Dispositionヘッダー設計
status: stable
generated:
  by: agent/gemini-3.7-flash
  at: 2026-08-14T09:30:00+09:00
tags:
  - domain
  - files
  - utf-8
  - performance
---

# File Handling & UTF-8 (ファイル処理と日本語対応)

## 1. 概要

Code Interpreter環境において、コード実行に伴うファイルの生成・ダウンロード、および日本語を含むファイル名の正常処理は極めて重要です。本APIでは、$O(N)$ の効率的なファイル走査と、RFC 5987に準拠したUTF-8ファイル名処理を実装しています。

## 2. $O(N)$ ファイルマッピング設計

セッション内のファイル一覧取得やダウンロード要求時の逆引き処理において、ファイル数が増加してもパフォーマンスが低下しないよう、$O(N^2)$ に陥るループ探索を排除し、$O(N)$ のハッシュマップ走査を採用しています。

```python
def get_file_id_mapping(session_id: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    セッション内の全ファイルに対して、一意な21文字Nanoidとの双方向マッピングをO(N)で構築。
    Returns:
        (name_to_id, id_to_name)
    """
    # ...
```

### 設計不変条件
* ファイル走査処理を $O(N^2)$ のネストループに戻さないこと。

## 3. 日本語ファイル名および UTF-8 処理仕様

### 3.1 コンテナ内 UTF-8 環境
`Dockerfile.rce` において以下の環境変数を設定し、PythonスクリプトやOSレベルでの日本語ファイル名の扱いや標準出力を保証します。
```dockerfile
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUTF8=1
```

### 3.2 RFC 5987 / RFC 6266 準拠の `Content-Disposition`
ブラウザやLibreChatクライアントへファイルを返送する際、日本語などのマルチバイト文字が文字化けしたり欠落したりするのを防ぐため、ASCIIフォールバックと `filename*=UTF-8''...` 形式を併用します。

```python
# 例: 日本語ファイル名のエンコード
ascii_filename = "download_file"
encoded_filename = quote(original_filename)
headers = {
    "Content-Disposition": f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"
}
```

## 4. 深いサブディレクトリ（ネスト構造）の走査とダウンロード

### 4.1 `list_files` による再帰的ファイル走査
`/mnt/data` 直下だけでなく、任意のサブディレクトリ（例: `/mnt/data/reports/analytics/2026/deep_plot.png`）に生成されたファイルも漏れなく検出するため、コンテナ内で `os.walk` を用いた再帰走査を実施しています。
* **不要ディレクトリの除外**: `.git`, `.venv`, `__pycache__`, `node_modules` などのシステム/隠しフォルダを自動除外。
* **相対パスの取得**: `/mnt/data` を起点とする相対パス（例: `reports/analytics/2026/deep_plot.png`）を取得して返却。

### 4.2 `{filename:path}` による階層パスのダウンロードルーティング
FastAPI の標準パスマッチング（`{filename}`）ではスラッシュ `/` が区切り文字とみなされて 404 になるため、`{filename:path}` ワイルドカードルートを採用しています。
```python
@app.get("/api/files/code/download/{session_id}/{filename:path}")
@app.get("/download/{session_id}/{filename:path}")
@app.get("/run/download/{session_id}/{filename:path}")
async def download_session_file(session_id: str, filename: str, ...):
    # ...
```

### 4.3 Nanoid 逆引きマッピングの階層パス維持 (`resolve_download_ids`)
`os.path.basename` による階層の切り落としを排除し、深い相対パスを維持したまま Nanoid ファイル ID との実ファイルパスの相互解決を行います。
* `Path.parts` によるパストラバーサル（`..`）防御を厳格に維持。
* `Content-Disposition` ヘッダー内のファイル名には `os.path.basename` を適用し、クライアントブラウザ側で保存名が破損しないよう正規化。

## 5. 作成プログラム・ソースコードファイルのダウンロード対応

AI がサンドボックス内で生成・保存したプログラムコードファイル（`.py`, `.sh`, `.R`, `.js`, `.ts`, `.sql`, `.html`, `.cpp` 等）は、画像やデータファイル（CSV）と同様に `/mnt/data` 配下で検知され、LibreChat チャット欄上でダウンロードカードやプレビューとして利用可能です。

* **MIME タイプ自動判別**: `mimetypes.guess_type` によりテキスト/ソースコード形式として安全に配信。
* **一時実行ファイルの分離**: 実行時の一時スクリプト（`exec_{uuid}.py`）は実行完了後に安全にクリーンアップされ、ユーザーが明示的に作成したプログラムファイルのみが一覧化されます。

## 6. 関連ドキュメント
* [Multi-Language Code Execution](./code-execution.md) - 多言語コード実行と画像キャプチャ
* [Nanoid ID Mapping](./nanoid-mapping.md) - ファイルIDのNanoidマッピング
* [Sandbox Image](../infrastructure/sandbox-image.md) - Dockerfile.rce の日本語フォント・ロケール設定
