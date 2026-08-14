---
type: Concept
title: File Handling & UTF-8
description: O(N)ファイル管理、日本語UTF-8ファイル名処理、Content-Dispositionヘッダー設計
status: active
timestamp: 2026-08-14T09:30:00+09:00
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

### 3.3 ストリーミングダウンロードの信頼性
ダウンロードエンドポイント（`/download/{session_id}/{file_id}`）では、FastAPIの `FileResponse` またはストリーミングレスポンスを使用し、適切な `Content-Length` および `Accept-Ranges` ヘッダーを付与することで、ブラウザでの大きなファイルダウンロード時の「ネットワークエラー」を防止します。

## 4. 関連ドキュメント
* [Nanoid ID Mapping](./nanoid-mapping.md) - ファイルIDのNanoidマッピング
* [Sandbox Image](../infrastructure/sandbox-image.md) - Dockerfile.rce の日本語フォント・ロケール設定
