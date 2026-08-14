---
type: Concept
title: Sandbox Image Design
description: Dockerfile.rce, Dockerfile.rce.gpu, Dockerfile.api の設計、非ルートユーザー、日本語フォント構成
status: active
timestamp: 2026-08-14T09:30:00+09:00
tags:
  - infrastructure
  - dockerfile
  - sandbox
  - security
---

# Sandbox Image Design (サンドボックス環境設計)

## 1. 概要

コードが実行されるサンドボックスコンテナイメージ（`Dockerfile.rce` / `Dockerfile.rce.gpu`）は、セキュリティ（最小特権）と使いやすさ（日本語環境、データサイエンスライブラリ）を両立するように設計されています。

## 2. `Dockerfile.rce` の設計と役割

```dockerfile
FROM python:3.12-slim

# 1. 日本語ロケールおよびUTF-8入出力の完全サポート
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUTF8=1

# 2. 最小特権原則に基づく非ルートユーザー作成
RUN groupadd -g 1000 sandboxuser && \
    useradd -m -u 1000 -g sandboxuser sandboxuser

WORKDIR /usr/src/app

# 3. 日本語フォント (IPA Gothic) とビルドパッケージ
COPY --chown=sandboxuser:sandboxuser rce_requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-ipafont-gothic \
    && rm -rf /var/lib/apt/lists/*

# 4. 依存ライブラリのインストール
RUN pip install --no-cache-dir --upgrade pip "setuptools>=78.1.1" wheel "msgpack>=1.2.1" jaraco.context && \
    pip install --no-cache-dir -r rce_requirements.txt

# 5. japanize-matplotlib のスタートアップ自動ロード
RUN printf "try:\n    import japanize_matplotlib\nexcept ImportError:\n    pass\n" > /usr/local/lib/python3.12/site-packages/sitecustomize.py

# 6. 作業用ディレクトリの作成と権限設定
RUN mkdir -p /mnt/data && chown sandboxuser:sandboxuser /mnt/data

USER sandboxuser

# 7. コンテナの常時待機プロセス
CMD ["tail", "-f", "/dev/null"]
```

## 3. 主要な設計ポイント

1. **非ルートユーザー (`sandboxuser: 1000`)**:
   コンテナ内のすべてのコード実行およびファイル作成は `sandboxuser` 権限で行われます。
2. **日本語フォントと自動適用**:
   `fonts-ipafont-gothic` を導入し、`sitecustomize.py` で `japanize_matplotlib` を自動インポートすることで、日本語グラフ描画時の文字化けと警告を排除します。
3. **常時待機 (`tail -f /dev/null`)**:
   コンテナを起動したまま待機させ、`docker exec` (API経由) で動的にスクリプトを実行することで、セッション間のファイル状態を維持しつつ、コンテナ起動オーバーヘッドをゼロ（ミリ秒応答）にします。

## 4. `Dockerfile.rce.gpu` (GPU対応)
NVIDIA CUDA ベースイメージ（`nvidia/cuda:12.4.1-runtime-ubuntu22.04` 等）を使用し、PyTorch 等の GPU 加速計算をサポートします。

## 5. 関連ドキュメント
* [Security Model](../architecture/security.md) - 多層防御アーキテクチャ
* [Multi-Language Code Execution](../domain/code-execution.md) - 多言語実行仕様
