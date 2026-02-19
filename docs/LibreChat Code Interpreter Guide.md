# **LibreChat Code Interpreter カスタムPython環境統合の詳細手順**

このドキュメントは、LibreChatのCode Interpreter機能が外部のカスタムPython API環境（FastAPI）で動作するための、セキュリティと機能の確からしさを確保した手順です。

# LibreChatに利用するLLM
```.env
# OpenAI API key
OPENAI_API_KEY={secret_api}
OPENAI_BASE_URL=https://api.ai.sakura.ad.jp/v1/
OPENAI_MODEL=gpt-oss-120b
```

**1\. Python環境の構築と依存関係の準備**

APIサーバー（FastAPI/Uvicorn）を動作させるための環境を確立します。このサーバー自体は、RCEを実行するホストとは分離されている必要があります。

### **a. 仮想環境（venv）でのセットアップ**

開発環境でのテスト用に適しています。

```Bash

python3 \-m venv libre\_env  
source libre\_env/bin/activate  
\# FastAPIとUvicornのインストール (requirements.txtに以下を追記)  
\# requirements.txt: fastapi, uvicorn, pydantic  
pip install \-r requirements.txt
```

### **b. Docker環境でのセットアップ（推奨）**

本番運用では、信頼性と移植性に優れたDockerコンテナでのデプロイが推奨されます 7。

| ファイル名 | 内容 | 備考 |
| :---- | :---- | :---- |
| requirements.txt | fastapi\[standard\] uvicorn\[standard\] pydantic | 標準的な依存関係 7 |
| Dockerfile | FROM python:3.11-slim WORKDIR /app COPY requirements.txt. RUN pip install \--no-cache-dir \-r requirements.txt COPY.. CMD \["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"\] | Uvicornの起動コマンドをExec形式で指定 7 |

```Bash

docker build \-t libre-python-api.  
docker run \-p 8000:8000 libre-python-api
```

## ---

**2\. セキュアなプロキシAPIの設計と実装（FastAPIの例）**

LibreChatが利用するカスタムエンドポイントは、最低限、以下のセキュリティと機能要件を満たす必要があります。

### **a. 認証付きエンドポイントの定義**

LibreChatの公式APIと同様に、カスタムエンドポイントもAPIキー認証を要求すべきです。ここでは、X-API-Keyヘッダーを使用した認証を組み込みます 1。

**main.pyのコード例（認証機能の追加）**

```Python

from fastapi import FastAPI, HTTPException, Security  
from fastapi.security import APIKeyHeader  
from pydantic import BaseModel  
import subprocess  
import os

\# 1\. 認証スキームの定義  
\# LibreChatがAPIキーを送信する場合に備え、認証ヘッダーを要求  
API\_KEY \= os.environ.get("CUSTOM\_RCE\_API\_KEY", "your\_secret\_key")  
api\_key\_header \= APIKeyHeader(name="X-API-Key", auto\_error=True)

async def get\_api\_key(api\_key: str \= Security(api\_key\_header)):  
    """APIキーが有効であることを検証する"""  
    \# 認証ロジック: 実際のキーと比較  
    if api\_key\!= API\_KEY:  
        raise HTTPException(status\_code=401, detail="Invalid API Key")  
    return api\_key

app \= FastAPI()

\# 2\. リクエストスキーマの定義  
class CodeRequest(BaseModel):  
    \# LibreChatのCode Interpreterは通常、コードに加えて言語やセッションIDを要求します。  
    \# 簡略化のためコードのみを定義しますが、実際には 'session\_id' も必要です。  
    code: str

\# 3\. コード実行エンドポイントのプロキシ  
\# 依存性注入により、リクエストがこの関数に到達する前に認証が完了している  
@app.post("/run")  
async def run\_code(req: CodeRequest, key: str \= Security(get\_api\_key)):  
    """サンドボックス化された環境（実際にはDockerコンテナ）へのコード実行をプロキシ"""  
    \# 警告: 以下のsubprocess.run()は、サンドボックス隔離機能がないため、  
    \# 開発/テスト目的でのみ使用し、本番環境では絶対に避けてください。  
    \# 本番環境では、ここで隔離されたDockerコンテナを起動・管理するロジックが必要です。  
    try:  
        result \= subprocess.run(  
            \["python3", "-c", req.code\],  
            capture\_output=True,   
            text=True,   
            timeout=10 \# 実行時間制限は必須  
        )  
        return {  
            "stdout": result.stdout,  
            "stderr": result.stderr,  
            "exit\_code": result.returncode  
        }  
    except Exception as e:  
        \# 例外処理: タイムアウトなど  
        return {"error": str(e)}
```

### **b. ファイルハンドリングとステートフルな実行（欠落機能）**

このシンプルな /run エンドポイントでは、LibreChatのCode Interpreterの主要な機能である**ファイルアップロード/ダウンロード**および**セッションベースのステート維持**に対応できません 1。

* **ファイル転送:** ファイルをアップロードするには、FastAPIに UploadFile を使用した **マルチパートフォームデータ**を受け付ける別のエンドポイント (@app.post("/upload") など) が必要です 9。  
* **ステート維持:** Code Interpreterは、分析結果や変数を次のコード実行に引き継ぐために session\_id を使用します。カスタムAPIは、この session\_id に基づいて、Dockerコンテナ（Jupyterカーネルなど）の状態を維持する複雑なロジックを実装する必要があります 1。

## ---

**3\. LibreChatの設定変更**

LibreChatインスタンスに、カスタムAPIをCode Interpreterの実行環境として使用するよう指示します。

### **LibreChat .envファイルの設定（推奨）**

librechat.yamlを使用する代わりに、機密性の高いURLを管理するために、.envファイルを使用することが推奨されます 11。

.envファイルに以下を追加または変更します。

コード スニペット

\# カスタムAPIのベースURLを指定  
\# Code Interpreterの公式な設定変数を使用  
LIBRECHAT\_CODE\_BASEURL=http://host.docker.internal:8000/run   
\# 注: Docker環境からホスト上のサービスを参照する場合、host.docker.internalを使用します。

\# LibreChatがカスタムAPIへ送信するAPIキーを定義  
\# このキーはステップ2aでFastAPIが検証するために使用されます  
LIBRECHAT\_CODE\_API\_KEY=your\_secret\_key\_from\_step2a

### **LibreChat librechat.yamlでのCode Interpreter有効化**

.envファイルでエンドポイントを定義している場合、librechat.yamlにはCode Interpreterを有効化する設定が必要になります。

```YAML
codeInterpreter:
  enabled: true
```

### **追加設定: 外部LLMプロバイダー（OpenAI互換）の統合**

Sakura AIやDeepSeekなどの外部OpenAI互換プロキシを統合する場合、`librechat.yaml` にカスタムエンドポイントを追加します。セキュリティ向上のため、APIキーやURLは環境変数経由で記述することを推奨します。

**1. .envファイルへの追記**
`.env` ファイルに以下の変数を追加します（お使いのプロバイダーに合わせて値を設定してください）。

```env
# External AI (OpenAI-Compatible)
EXTERNAL_API_URL=https://api.ai.sakura.ad.jp/v1/
EXTERNAL_API_KEY=your_actual_api_key
EXTERNAL_LLM_MODEL=Qwen3-Coder-30B-A3B-Instruct
```

**2. librechat.yaml の設定**
`endpoints.custom` セクションにプレースホルダー `${VARIABLE_NAME}` を用いて登録します。

```YAML
version: "1.1.5"
endpoints:
  custom:
    - name: "SakuraAI"
      apiKey: "${EXTERNAL_API_KEY}"
      baseURL: "${EXTERNAL_API_URL}"
      models:
        default: ["${EXTERNAL_LLM_MODEL}"]
        fetch: true
      titleConvo: true
      summarize: true
      modelDisplayLabel: "Sakura Model"
```

LibreChatを再起動して設定を反映させます。

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d
```

## ---

**4\. ファイル添付の有効化**

LibreChatのUIからファイルをカスタムCode Interpreterに送信できるように、ファイル機能を有効化します。

### **a. librechat.yamlでのファイル設定**

ファイルアップロードを有効化します。

```YAML

fileConfig:  
  enabled: true  
  \# ここで指定するuploadDirはLibreChatサーバー側のアップロードディレクトリです。  
  \# この設定が有効でも、ファイルの実処理はカスタムCode Interpreter API側で行われる必要があります。  
  uploadDir:./uploads 
```
### **b. 依存管理の確実化**

カスタムAPI（FastAPI）に必要な依存関係を requirements.txt に記述し、環境の再現性を確保します 7。

```Bash

\# 必要なライブラリを追加  
pip install fastapi uvicorn pydantic python-multipart  
\# 環境を固定  
pip freeze \> requirements.txt
```
## ---

**🔐 セキュリティ対策（必須）**

このカスタムRCEゲートウェイの運用は、以下のセキュリティ対策なしには実行してはいけません。

| 対策 | 目的 | 実装の推奨事項 |
| :---- | :---- | :---- |
| **RCEサンドボックス化** | ホストOSへの不正アクセスを完全に防ぐ 2 | **必須:** Docker-in-Dockerまたはコンテナオーケストレーション（例: docker-py SDK）を使用して、**各実行を隔離された使い捨てのコンテナ**で実行する。 |
| **実行時間・メモリ制限** | DoS攻撃やリソース枯渇を防ぐ 5 | Docker run コマンドで \--memory や \--cpu-quota を設定する 6。FastAPI側でも timeout を設定する（ステップ2aで実施済み）。 |
| **認証付きAPI** | サービスの不正利用を防ぐ 12 | **必須:** ステップ2aで示したように、FastAPIに APIKeyHeader を使用した認証ロジックを実装し、LIBRECHAT\_CODE\_API\_KEY を検証する 8。 |
| **HTTPSの強制** | APIキーを含む通信内容を保護する 13 | ロードバランサ（Nginx, Traefik）やリバースプロキシを使用して、APIサービスへのすべてのアクセスでTLS/SSLを強制する。 |

#### **引用文献**

1. Code Interpreter API \- LibreChat, 12月 6, 2025にアクセス、 [https://www.librechat.ai/docs/features/code\_interpreter](https://www.librechat.ai/docs/features/code_interpreter)  
2. sastava007/RCE-Pipeline \- GitHub, 12月 6, 2025にアクセス、 [https://github.com/sastava007/RCE-Pipeline](https://github.com/sastava007/RCE-Pipeline)  
3. Remote Code Execution (RCE) | Types, Examples & Mitigation | Imperva, 12月 6, 2025にアクセス、 [https://www.imperva.com/learn/application-security/remote-code-execution/](https://www.imperva.com/learn/application-security/remote-code-execution/)  
4. Top 10 Ways to Achieve Remote Code Execution (RCE) on Web Applications, 12月 6, 2025にアクセス、 [https://fdzdev.medium.com/top-10-ways-to-achieve-remote-code-execution-rce-on-web-applications-d923246b916b](https://fdzdev.medium.com/top-10-ways-to-achieve-remote-code-execution-rce-on-web-applications-d923246b916b)  
5. Resource constraints \- Docker Docs, 12月 6, 2025にアクセス、 [https://docs.docker.com/engine/containers/resource\_constraints/](https://docs.docker.com/engine/containers/resource_constraints/)  
6. Running containers \- Docker Docs, 12月 6, 2025にアクセス、 [https://docs.docker.com/engine/containers/run/](https://docs.docker.com/engine/containers/run/)  
7. FastAPI in Containers \- Docker, 12月 6, 2025にアクセス、 [https://fastapi.tiangolo.com/deployment/docker/](https://fastapi.tiangolo.com/deployment/docker/)  
8. Security Tools \- FastAPI, 12月 6, 2025にアクセス、 [https://fastapi.tiangolo.com/reference/security/](https://fastapi.tiangolo.com/reference/security/)  
9. Request Files \- FastAPI, 12月 6, 2025にアクセス、 [https://fastapi.tiangolo.com/tutorial/request-files/](https://fastapi.tiangolo.com/tutorial/request-files/)  
10. A FastAPI-based sandboxed Python code execution environment using Jupyter kernels \- GitHub, 12月 6, 2025にアクセス、 [https://github.com/anukriti-ranjan/sandboxed-jupyter-code-exec](https://github.com/anukriti-ranjan/sandboxed-jupyter-code-exec)  
11. env File Configuration \- LibreChat, 12月 6, 2025にアクセス、 [https://www.librechat.ai/docs/configuration/dotenv](https://www.librechat.ai/docs/configuration/dotenv)  
12. A simple Python FastAPI template with API key authentication \- timberry.dev, 12月 6, 2025にアクセス、 [https://timberry.dev/fastapi-with-apikeys](https://timberry.dev/fastapi-with-apikeys)  
13. How to secure APIs built with FastAPI: A complete guide \- Escape DAST, 12月 6, 2025にアクセス、 [https://escape.tech/blog/how-to-secure-fastapi-api/](https://escape.tech/blog/how-to-secure-fastapi-api/)