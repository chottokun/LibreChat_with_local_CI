RCEサンドボックス環境で利用できるライブラリを事前にインストールされたものに限定し、その設定を柔軟に制御したいというご要望は、セキュリティと運用の観点からベストプラクティスです。

これを実現する最も効果的な方法は、**RCEサンドボックスとして使用するDockerイメージを完全にカスタムビルド**し、そのイメージ内で利用可能なライブラリを`Dockerfile`で厳密に定義することです。

以下に、このカスタムRCE環境の構築と、FastAPIゲートウェイとの連携方法を明確にします。

-----

## I. RCEサンドボックス環境のカスタム構築 (Docker Image)

この手順は、ユーザーコードが実行される隔離環境（サンドボックス）を作成するためのものであり、**セキュリティを担保する要**となります。利用したい任意のライブラリは、ここで定義します。

### 1\. RCE環境の`Dockerfile`の準備

サンドボックスコンテナのベースイメージとして、Pythonの基本イメージを使用し、必要なライブラリを`pip`でインストールする手順を定義します。

| ファイル名 | 内容 | 備考 |
|---|---|---|
| `rce_requirements.txt` | `pandas`<br>`numpy`<br>`scipy`<br>`matplotlib`<br>`ipykernel` | **利用したい任意のライブラリ**を記述します。Jupyter Kernelアプローチでは、カーネル機能のために`ipykernel`が必須です [1]。 |
| `Dockerfile.rce` | 以下の手順を参照 | RCEコンテナイメージのビルド定義ファイル。 |

**`Dockerfile.rce` の内容**

```dockerfile
# 1. ベースイメージ: Pythonの軽量な環境を選択
FROM python:3.11-slim

# 2. 作業ディレクトリを定義
WORKDIR /usr/src/app

# 3. RCE環境で利用したいライブラリをインストール
# rce_requirements.txtをコピーし、pipでインストール
COPY rce_requirements.txt.
RUN pip install --no-cache-dir -r rce_requirements.txt 

# 4. RCEカーネルの起動コマンド (Jupyter Kernelの場合)
# このコマンドは、FastAPIがカーネルを起動するために必要です。
# 実際には、カーネル起動はFastAPI側からDocker SDK経由で行われますが、
# このイメージがカーネル実行に必要な環境を提供します。
# CMD ["python", "-m", "ipykernel_launcher"] 
```

### 2\. RCEコンテナイメージのビルド

このカスタムイメージをビルドし、FastAPIゲートウェイからアクセスできるDockerレジストリ、またはローカルのDockerホストに配置します。

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest.
```

この`custom-rce-kernel:latest`イメージには、`pandas`, `numpy`, `matplotlib`など、あなたが定義した任意のライブラリのみが含まれ、ユーザーはその外部のライブラリにアクセスすることはできません。

-----

## II. FastAPIゲートウェイの実装と連携ロジック

FastAPIゲートウェイ（プロキシAPI）は、LibreChatからのリクエストを受け取り、上記のカスタムイメージを使用してセッション固有の隔離コンテナを起動・管理します。

### 1\. APIゲートウェイのライブラリ設定

FastAPIコンテナでDocker APIを操作するために、`docker`ライブラリ（`docker-py`）が必要です。

**`requirements.txt` (FastAPIゲートウェイ用)**

```
fastapi[standard]
uvicorn[standard]
pydantic
python-multipart
docker
```

### 2\. コード実行ロジックの実装（`main.py`）

`/run`エンドポイントは、`session_id`を受け取ると、Docker SDK (`docker-py`) を使用してカスタムRCEイメージを実行します。

```python
import docker
#... (他のインポート, FastAPI初期化, 認証ロジック)

# Dockerクライアントの初期化 (FastAPIがDockerデーモンと通信できるように設定されている必要があります)
DOCKER_CLIENT = docker.from_env()

# カスタムRCEイメージ名を設定
RCE_IMAGE_NAME = "custom-rce-kernel:latest"

# 1. セッションデータの永続化設定
# セッション固有のファイル、変数、環境の状態を維持するためのコンテナ管理クラス
class KernelManager:
    # 実際の実装では、セッションIDとコンテナID、カーネル接続情報をマッピングする辞書やDBが必要
    active_kernels = {} 
    
    def start_new_kernel_in_container(self, session_id: str, image_name: str, cpu_limit: str = '0.5', mem_limit: str = '512m'):
        """カスタムRCEイメージを使用して新しいカーネルコンテナを起動し、リソースを制限する"""
        
        # セッション専用のDocker Volumeを定義 (ファイルの永続化のため)
        volume_name = f'librechat_vol_{session_id}'

        # Dockerコンテナの起動 (Jupyter Kernelとして)
        container = DOCKER_CLIENT.containers.run(
            image=image_name,
            # RCEコンテナの起動コマンドをカーネル起動に合わせる
            command='jupyter-kernel-launch-command', # 適切なカーネル起動コマンド
            
            # ** 必須: リソース制限の適用 **
            mem_limit=mem_limit,       # メモリ制限を適用 
            cpus=float(cpu_limit),     # CPU使用率制限を適用 (例: 0.5 = 50% CPU) 
            
            # ** 必須: ファイルシステム隔離とセッション維持 **
            volumes={
                volume_name: {'bind': '/mnt/session_data', 'mode': 'rw'}
            },
            # 必須: ネットワーク隔離 (ホストや外部ネットワークへのアクセスを禁止)
            network_disabled=True, 
            detach=True,
            remove=True,
        )
        # 起動したコンテナの情報を保存 (active_kernelsにsession_idとコンテナIDをマッピング)
        self.active_kernels[session_id] = container.id
        #... ここでカーネル接続情報を取得し、セッションに紐づけるロジック
        return container.id

kernel_manager = KernelManager() # KernelManagerのインスタンス化

@app.post("/run")
async def run_code(req: CodeRequest, key: str = Security(get_api_key)):
    """LibreChatからのコード実行リクエストを処理"""
    
    # 1. セッションカーネルの確認と起動
    if req.session_id not in kernel_manager.active_kernels:
        # 該当セッションが存在しない場合、カスタムイメージで新規にカーネルを起動
        kernel_manager.start_new_kernel_in_container(req.session_id, RCE_IMAGE_NAME)
        
    # 2. 既存のカーネルにコードを送信
    # ユーザーが要求したコードを、req.session_idに対応するカーネルに送信する
    # このカーネルは、事前にインストールされたライブラリのみを利用できる
    execution_result = await kernel_manager.execute_code(req.session_id, req.code)

    return {
        "stdout": execution_result.stdout,
        "stderr": execution_result.stderr,
        "exit_code": execution_result.exit_code
    }
```

この構築方法により、FastAPIゲートウェイは、**あなたが事前に定義し、利用を許可したライブラリのみ**を含むカスタムイメージ (`custom-rce-kernel:latest`) をサンドボックスとして使用することが保証されます。