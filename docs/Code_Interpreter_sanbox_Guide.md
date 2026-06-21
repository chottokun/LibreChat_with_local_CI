# RCEサンドボックス環境（Docker）のカスタム構築と動作設計ガイド

本ドキュメントは、LibreChatに提供されるCode Interpreter API（Custom RCE）が、どのようにして隔離されたDockerサンドボックス環境を動的に管理し、セキュアかつ日本語に対応したコード実行を実現しているかを解説した技術ガイドです。

---

## 1. 隔離モデルの基本設計 (docker exec アプローチ)

本APIでは、Jupyter Kernelアプローチのような複雑な接続維持（ZMQポート管理等）を避け、シンプルで堅牢な **`docker exec` 実行モデル** を採用しています。

* **常時稼働コンテナ**: 
  セッションごとに起動されるDockerコンテナは、`tail -f /dev/null` をエントリポイントとしてバックグラウンドで常時起動状態を維持します。これにより、起動コストを最小限に抑えつつ、ファイルシステムの状態を保持します。
* **動的実行**:
  ユーザーから送信されたプログラムコードは、API（FastAPI）側で一時スクリプトファイルとしてパッケージ化（tarストリーム化）され、Docker API（`put_archive`）を介してコンテナ内の作業ディレクトリ `/mnt/data` へ安全に転送されます。その後、`docker exec` 相当の API（`exec_run`）によって指定言語のインタプリタ（Python, Bash, R）が動的に起動され、コードが実行されます。
* **安全なファイル取得**:
  実行後に生成されたファイルや標準出力は、再び Docker API またはボリュームマウント経由で API ゲートウェイに引き渡され、ユーザーへ安全に返送されます。

---

## 2. サンドボックス環境の構築 (`Dockerfile.rce`)

ユーザーのコードが実行される隔離環境（サンドボックス）の設計図です。セキュリティの最小特権原則と、日本語ファイル名および日本語のグラフ描画に対応するための最適化が施されています。

### `Dockerfile.rce` の設計と役割

```dockerfile
FROM python:3.11-slim

# 1. 日本語ファイル名およびUTF-8入出力の完全サポート
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUTF8=1

# 2. 最小特権原則に基づく非ルートユーザーの作成
RUN groupadd -g 1000 sandboxuser && \
    useradd -m -u 1000 -g sandboxuser sandboxuser

WORKDIR /usr/src/app

# 3. 必要なシステムパッケージと日本語フォントの導入
COPY --chown=sandboxuser:sandboxuser rce_requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-ipafont-gothic \
    && rm -rf /var/lib/apt/lists/*

# 4. 依存ライブラリのインストール
RUN pip install --no-cache-dir --upgrade pip setuptools wheel jaraco.context && \
    pip install --no-cache-dir -r rce_requirements.txt

# 5. japanize-matplotlib のスタートアップ自動ロード設定
# これにより、ユーザーコード側で明示的に import しなくても、Matplotlib の日本語文字化けとフォント警告を自動的に回避します。
RUN printf "try:\n    import japanize_matplotlib\nexcept ImportError:\n    pass\n" > /usr/local/lib/python3.11/site-packages/sitecustomize.py

# 6. 作業用ボリュームディレクトリの作成と権限移譲
RUN mkdir -p /mnt/data && chown sandboxuser:sandboxuser /mnt/data

USER sandboxuser

# 7. コンテナの常時稼働プロセスの定義
CMD ["tail", "-f", "/dev/null"]
```

### この設計のメリット：
1. **セキュリティ (非ルート制限)**:
   コンテナ内での実行はすべて `sandboxuser` (UID/GID 1000) に制限されています。万が一、ユーザーコードによりコンテナのエスケープや脆弱性を突いた攻撃が試みられても、ホストの root 権限を奪取することは極めて困難です。
2. **日本語グラフ描画の自動最適化**:
   `fonts-ipafont-gothic` フォントを導入し、Matplotlib の描画時に自動的に `japanize_matplotlib` を読み込むことで、ユーザーが日本語を含むラベルやタイトルを出力しても `DejaVu Sans` 等の豆腐（文字化け）や警告メッセージを出さずに、美しい日本語グラフを出力できます。

---

## 3. APIゲートウェイ（`main.py`）側のコンテナ制御とセキュリティ制限

FastAPI側は、Docker SDK for Python (`docker-py`) を使用して、コンテナの起動パラメータで強固なリソース制限およびネットワーク隔離を適用します。

### `KernelManager` で行われる主要な設定パラメータ

```python
def start_new_container(self, session_id: str, external_session_id: Optional[str] = None):
    # 同時最大セッション数制限（サービス容量上限の制御）
    if len(self.active_kernels) >= RCE_MAX_SESSIONS:
        raise HTTPException(status_code=503, detail="Server is at capacity.")

    config = self._get_container_config()
    volumes = self._prepare_volumes(session_id)

    container = DOCKER_CLIENT.containers.run(
        image=RCE_IMAGE_NAME,
        command="tail -f /dev/null",  # コンテナの常時起動
        detach=True,
        remove=True,                  # 停止時にコンテナリソースを自動クリーンアップ
        name=f"rce_{session_id}_{uuid.uuid4().hex[:6]}",
        working_dir="/mnt/data",
        labels={
            "managed_by": "librechat-rce",
            "session_id": session_id,
            "external_session_id": external_session_id or ""
        },
        environment={"PYTHONUNBUFFERED": "1"},
        volumes=volumes,
        **config
    )
    container.exec_run(cmd=["mkdir", "-p", "/mnt/data"])
    return container
```

### セキュリティとリソース管理のパラメータ詳細

1. **メモリ制限 (`mem_limit`)**:
   環境変数 `RCE_MEM_LIMIT`（デフォルト `512m`）でコンテナあたりの物理メモリ上限を設定。悪意のあるプログラムによるメモリ無限確保（DoS攻撃）からホストシステムを保護します。
2. **CPU制限 (`nano_cpus`)**:
   環境変数 `RCE_CPU_LIMIT`（デフォルト `500000000` = 0.5 CPU）でCPU割り当てを設定。コンテナ内での無限ループ（`while True:`）等の実行がホストの全CPUコアを占有するのを防止します。
3. **ネットワーク隔離 (`network_disabled=True`)**:
   環境変数 `RCE_NETWORK_ENABLED`（デフォルト `false`）により、コンテナ内部からの外部インターネット通信を完全に遮断。サンドボックス内部で取得したデータやAPIキーなどの機密情報を外部の悪意あるサーバーへ送信（データ漏洩）する不正アクセスを防ぎます。
4. **データの永続化と転送モード**:
   * **ボリュームマウントモード**:
     ホスト側のデータ保存先ディレクトリ (`RCE_DATA_DIR`) が指定されている場合、ホストの専用セッションフォルダをコンテナの `/mnt/data` へ直接マウントします。これにより高速な読み書きと永続化が可能になります。
   * **put_archive モード（標準）**:
     ボリュームをマウントしない構成の場合、ファイルを `tar` アーカイブ化して Docker API 経由でコンテナへプッシュします。特別なホストパーミッションの設定なしで動作する利便性があります。