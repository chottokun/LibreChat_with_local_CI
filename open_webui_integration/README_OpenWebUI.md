# Open WebUI用 Code Interpreter 統合ガイド

このディレクトリには、Open WebUIで LibreChat Custom RCE (Code Interpreter) を利用するためのツール一式が含まれています。

## 構成ファイル

- `rce_workspace_tool.py`: Open WebUIに登録するツール本体のスクリプト。
- `docker-compose.openwebui.yml`: Open WebUIを起動するためのDocker Composeファイル。

## セットアップ手順

### 1. RCEバックエンドの起動

まず、Code Interpreter API本体を起動します。

```bash
docker build -f Dockerfile.rce -t custom-rce-kernel:latest .
docker compose up -d
```

### 2. Open WebUIの起動

Open WebUIを起動します。

```bash
docker compose -f docker-compose.openwebui.yml up -d
```
起動後、ブラウザで `http://localhost:3000` にアクセスし、アカウントを作成・ログインしてください。

### 3. ツールの登録

1. Open WebUIの画面左下のプロフィールアイコン -> **Workspace** -> **Tools** を選択します。
2. **[Create Tool]** (または `+` ボタン) をクリックします。
3. `open_webui_integration/rce_workspace_tool.py` の内容をコピーし、エディタに貼り付けます。
4. **[Save]** をクリックして保存します。

### 4. Valveの設定 (接続情報)

1. 保存したツールの右側にある **[Valves]** (歯車アイコン) をクリックします。
2. 以下の設定を行います：
   - `RCE_API_BASE_URL`: `http://host.docker.internal:8000` (Open WebUIがDocker上で動いている場合)
   - `RCE_API_KEY`: API本体の起動に使用した `LIBRECHAT_CODE_API_KEY` の値。
3. **[Submit]** をクリックします。

### 5. チャットでの利用

1. 新しいチャットを開始します。
2. モデル選択メニューで、ツールをサポートしているモデルを選択します。
3. `+` ボタン（または `/` コマンド）から、登録したツール（例：`execute_code`）を有効にします。
4. 「1から100までの合計を計算して」や「グラフを描画して」と指示すると、Code Interpreterが実行されます。

## 特徴

- **日本語ファイル名の維持**: アップロードされたファイルの日本語名を保持したままサンドボックスに転送します。
- **グラフ・画像のインライン表示**: 生成された画像（matplotlib, seaborn等）を自動的にBase64エンコードし、チャット画面内に直接表示します。
- **セッション分離**: チャットスレッドごとに独立したコンテナが割り当てられます。

## 高度な設定

### セッションの有効期限延長

長時間のデータ分析を行う場合、デフォルトのセッション有効期限（1時間）では短い場合があります。これを延長するには、API側の起動時に環境変数 `RCE_SESSION_TTL` を設定します。

```bash
# 例: 24時間 (86400秒) に延長
export RCE_SESSION_TTL=86400
docker compose up -d
```

## 注意事項

- Open WebUIからAPIにアクセスできない場合は、`docker-compose.openwebui.yml` の `extra_hosts` 設定や、API側のポート公開設定を確認してください。
