---
type: Concept
title: Sandbox Image Design
description: Dockerfile.rce, Dockerfile.rce.gpu, Dockerfile.api の設計、非ルートユーザー、日本語フォント構成
status: stable
generated:
  by: agent/gemini-3.7-flash
  at: 2026-08-14T09:30:00+09:00
tags:
  - infrastructure
  - dockerfile
  - sandbox
  - security
---

# Sandbox Image Design (サンドボックス環境設計)

## 1. 概要

コードが実行されるサンドボックスコンテナイメージ（`Dockerfile.rce` / `Dockerfile.rce.gpu`）は、セキュリティ（最小特権）と使いやすさ（日本語環境、データサイエンスライブラリ）を両立するように設計されています。

## 2. `Dockerfile.rce` (CPU版) の設計と役割

Ubuntu 24.04 上で `uv` を用いてスタンドアロンの **Python 3.13** 仮想環境をビルドし、実行ステージへ最小限の構成のみをコピーするマルチステージビルドを採用しています。

```dockerfile
# Stage 1: Builder using uv for Python 3.13
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv python install 3.13
RUN uv venv /opt/venv --python 3.13

ENV PATH="/opt/venv/bin:$PATH"
COPY rce_requirements.txt .
RUN uv pip install --no-cache-dir "setuptools>=83.0.0" wheel -r rce_requirements.txt

# Stage 2: Minimal Runtime on Ubuntu 24.04
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUTF8=1
ENV PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates fonts-ipafont-gothic && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/python /opt/python
COPY --from=builder /opt/venv /opt/venv

RUN userdel -r ubuntu 2>/dev/null || true && \
    groupadd -g 1000 sandboxuser && \
    useradd -m -u 1000 -g sandboxuser sandboxuser

RUN printf "try:\n    import japanize_matplotlib\nexcept ImportError:\n    pass\n" > /opt/venv/lib/python3.13/site-packages/sitecustomize.py
RUN mkdir -p /mnt/data && chown sandboxuser:sandboxuser /mnt/data

USER sandboxuser
WORKDIR /mnt/data
CMD ["tail", "-f", "/dev/null"]
```

## 3. 主要な設計ポイント

1. **Ubuntu 24.04 & Python 3.13 統一**:
   CPU 版・GPU 版のベース OS を Ubuntu 24.04 に統一しつつ、最新の Python 3.13 実行環境を共通で提供します。
2. **非ルートユーザー (`sandboxuser: 1000`)**:
   コンテナ内のすべてのコード実行およびファイル作成は `sandboxuser` 権限で行われます。
3. **日本語フォントと自動適用**:
   `fonts-ipafont-gothic` を導入し、`sitecustomize.py` で `japanize_matplotlib` を自動インポートすることで、日本語グラフ描画時の文字化けと警告を排除します。
4. **常時待機 (`tail -f /dev/null`)**:
   コンテナを起動したまま待機させ、`docker exec` (API経由) で動的にスクリプトを実行することで、セッション間のファイル状態を維持しつつ、コンテナ起動オーバーヘッドをゼロ（ミリ秒応答）にします。

## 4. `Dockerfile.rce.gpu` (GPU対応版)

NVIDIA 公式の `nvidia/cuda:12.6.0-runtime-ubuntu24.04` をベースにしたマルチステージ構成です。CPU版と同一の Python 3.13 仮想環境および日本語環境を維持しながら、GPU アクセラレーション（PyTorch 等）を利用できます。

`.env` で以下のように設定することで CPU/GPU をシームレスに切り替え可能です：
```bash
# CPU版利用時
RCE_IMAGE_NAME=custom-rce-kernel:latest
RCE_GPU_ENABLED=false

# GPU版利用時
RCE_IMAGE_NAME=custom-rce-kernel:gpu
RCE_GPU_ENABLED=true
```

## 5. 関連ドキュメント
* [Security Model](../architecture/security.md) - 多層防御アーキテクチャ
* [Multi-Language Code Execution](../domain/code-execution.md) - 多言語実行仕様
