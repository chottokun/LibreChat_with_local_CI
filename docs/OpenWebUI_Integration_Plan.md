# Open WebUI用 Code Interpreter 統合計画書

## 1. LibreChat対応との両立（共存）についての考察

**結論から言うと、LibreChat対応との「完全な両立・共存」は可能です。**
機能的なトレードオフや、どちらか一方を犠牲にする必要はありません。

### 深い考察と両立可能な理由
既存のバックエンド（`main.py`）は、独立したREST API（`/exec`, `/upload` など）として実装されています。
* **セッションの独立性**: バックエンド側では送られてきた `session_id` をもとに、コンテナの起動やホスト側のボリューム（`/app/sessions/{session_id}`）を割り当てます。LibreChatは通常Nano IDベースのIDを送信しますが、Open WebUIからは `__metadata__["chat_id"]` などを送信します。これらは文字列として区別されるため、それぞれのチャット画面のセッションがバックエンド上で混線・干渉することは構造上あり得ません。
* **クライアント・アグノスティック**: バックエンド自体は「リクエストがLibreChatから来たのか、Open WebUIのツールから来たのか」を意識しません。正しいAPIキー（`X-Api-Key`）さえ付与されていれば、等しく隔離されたPythonコンテナ環境を提供します。

### 共存運用時の注意点（運用上の課題）
プログラム上の競合はありませんが、以下の運用面での注意が必要です。
1. **リソース枯渇のリスク**: 両方のフロントエンド（LibreChatとOpen WebUI）から同時に多数のCode Interpreterセッションが要求された場合、ホストマシン（Docker）のメモリ（1コンテナにつき512MB）やCPU制限（0.5コア）に到達しやすくなります。同時利用者が多い環境では、Dockerホストのスケールアップが必要です。
2. **アイドリングの共有仕様と解決策**: バックエンドは環境変数 `RCE_SESSION_TTL`（デフォルト3600秒＝1時間）を経過したアクセスがないコンテナを自動破棄します（`clean_idle_sessions`）。
   * **提案**: 長時間の分析などを行うOpen WebUIユーザーにとって1時間での破棄は短すぎる可能性があります。これに対処するため、`.env` および docker-composeの構成ファイルで `RCE_SESSION_TTL=86400`（24時間）のように明示的にタイムアウトを延長する設定をマニュアルに追記し、ユーザーが用途に合わせて柔軟に変更できるようにします。バックエンド自体のコード変更は不要です。
3. **認証キーの共有**: どちらのUIからも同じ `LIBRECHAT_CODE_API_KEY` を利用してバックエンドにアクセスすることになります。ローカルや社内ネットワークでの運用であれば問題ありませんが、キーの漏洩には注意が必要です。

---

## 2. 開発とテスト環境の基本方針 (Docker Compose構成)

LibreChatとOpen WebUIを同時に起動するのではなく、「どちらかを選択して起動・テストできる」ようにDocker Composeの構成を整理・追加します。

既存の `docker-compose.yml` はRCEバックエンド専用として独立させ、フロントエンド用の構成ファイルを別名で用意します。

* **`docker-compose.yml`**: RCEバックエンド（API + Proxy）のみを定義（既存のまま）
* **`docker-compose.librechat.yml`**（既存の `docker-compose.full.yml` をリネーム推奨）: LibreChat + DB群を定義
* **`docker-compose.openwebui.yml`**（★新規作成）: Open WebUIのみを定義

これにより、テスト時の起動コマンドを以下のように使い分けることができます：
* Open WebUIでテストする場合: `docker compose -f docker-compose.yml -f docker-compose.openwebui.yml up -d`
* LibreChatでテストする場合: `docker compose -f docker-compose.yml -f docker-compose.librechat.yml up -d`

ユーザーから提示された要件定義に則り、既存のリポジトリ（RCEバックエンド本体）には手を加えません。
Open WebUIからこのRCE APIを安全かつ透過的に呼び出すための「ブリッジ」として機能するPythonツール（Workspace Tools）を開発し、同梱します。

## 3. リポジトリ構成の変更計画

リポジトリルートに `open_webui_integration` ディレクトリを新設し、以下のファイルを追加します。

```text
LibreChat_with_local_CI/
├── api/                 # 既存のRCEバックエンド（変更なし）
├── open_webui_integration/      # ★新規追加ディレクトリ
│   ├── README_OpenWebUI.md      # Open WebUIへの登録・設定手順書
│   └── rce_workspace_tool.py    # ★新規作成：Open WebUIツール本体
```

---

## 4. `rce_workspace_tool.py` の実装機能要件

### 4.1. 接続情報の動的設定 (Valves)
Open WebUIのツール画面から管理者がGUIで設定できるよう、Pydanticベースの `Valves` を実装します。
* `RCE_API_BASE_URL`: デフォルト `http://host.docker.internal:8000` (Open WebUIがDocker上で動いている場合を想定)
* `RCE_API_KEY`: バックエンドに渡す認証キー（環境変数対応）

### 4.2. オリジナル日本語ファイル名の透過的アップロード
LLMツール関数（例：`execute_code_interpreter`）の引数に、Open WebUIのシステム予約引数 `__files__` を受け取るようにします。
1. `__files__` 内の各ファイルメタデータからオリジナルの `filename` (日本語含む) を抽出。
2. `content` に含まれるBase64文字列（またはバイナリ）をデコード。
3. `httpx` 等を利用し、マルチパートフォーム(`multipart/form-data`)としてRCEバックエンドの `/upload` エンドポイントへ POST 送信。

### 4.3. セッション管理の連携
システム予約引数 `__metadata__` (または `__user__`) を受け取り、`__metadata__.get("chat_id")` を `session_id` としてRCEバックエンドへ引き渡します。
これにより、チャットスレッドごとに独立したコンテナサンドボックス環境を自動的に確保します。

### 4.4. コード実行と標準出力のハンドリング
RCEの `/exec` エンドポイントに対してHTTP POSTリクエストを行い、レスポンスから `stdout` および `stderr` を抽出し、LLMが理解できる文字列として返却します。

### 4.5. 生成ファイル（画像・グラフなど）のインライン描画
実行結果に新しく生成されたファイル（画像等）が含まれる場合、以下のフローをツール内に実装します：
1. RCEバックエンドの `/files` や `/download/{session_id}/{filename}` からバイナリを取得。
2. 取得したバイナリをBase64文字列にエンコードし、`data:image/png;base64,...` のデータURIスキーム形式に変換。
3. `![Generated Image](data:image/png;base64,...)` のようなMarkdown形式をツールの返り値に結合し、Open WebUIのチャット画面上に直接画像をレンダリングさせる。

### 4.6. 非同期通信とセキュリティ
* ネットワーク処理によるOpen WebUIのメインプロセスのブロッキングを防ぐため、通信には `httpx.AsyncClient` などの非同期ライブラリを使用します。
* ツールのdocstringには「任意のコードがDockerコンテナ内で実行される」旨の強力な警告を含め、システムプロンプトとしてLLMに機能制約を明示します。

---

## 5. 今後のステップ (Verification Plan)

ユーザーからの承認が得られ次第、以下の作業を実行します。
1. `open_webui_integration/rce_workspace_tool.py` のソースコードのコーディング。
2. `open_webui_integration/README_OpenWebUI.md` の作成（Open WebUIでのツール登録方法、Valve設定方法の解説）。
3. ユーザーにOpen WebUI環境での動作確認（特に画像レンダリングや日本語ファイル名の維持）を依頼。
