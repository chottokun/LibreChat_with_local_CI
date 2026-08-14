---
type: Concept
title: Reverse Proxy & SSL Design (Nginx)
description: Nginx を用いた SSL/TLS 終端、SAN 証明書、WebSocket/SSE リアルタイムストリーミング、将来の OIDC/SSO 連携設計
status: stable
generated:
  by: agent/gemini-3.7-flash
  at: 2026-08-14T11:00:00+09:00
tags:
  - infrastructure
  - nginx
  - ssl
  - oidc
  - reverse-proxy
---

# Reverse Proxy & SSL Design (Nginx 構成)

## 1. 概要

本システムでは、リバースプロキシとして **Nginx**（`nginx:alpine`）を採用し、以下の機能を提供します：
1. **HTTP → HTTPS 自動リダイレクト**: ポート 80 への平文 HTTP アクセスを自動的にポート 443（HTTPS）へ 301 恒久転送。
2. **SSL/TLS 終端**: IP アドレス直接アクセス（例: `https://192.168.1.100`）およびローカルホスト（`https://localhost`）での安全な暗号化通信。
3. **リアルタイムストリーミング**: AI の文字生成（Server-Sent Events: SSE）および WebSocket の低遅延中継（`proxy_buffering off`）。
4. **Artifacts (Sandpack Bundler) 連携**: ポート 8443 による React/HTML 等の UI 描画コンテナの HTTPS 化。
5. **将来の OIDC / SSO 拡張性**: Keycloak、Entra ID (Azure AD)、Google Workspace 等との連携基盤。

---

## 2. アーキテクチャ構成

```
[ ブラウザ / クライアント (LAN / Local) ]
        |
        +-- HTTP  (Port 80)   --> 301 Redirect to HTTPS
        +-- HTTPS (Port 443)  --> LibreChat 本体 (Port 3080)
        +-- HTTPS (Port 8443) --> Sandpack Bundler (Port 80)
        v
+-----------------------------------------------+
|         Nginx (Reverse Proxy Container)       |
|  - Port 80: HTTP -> HTTPS 301 Redirect        |
|  - Port 443: SSL Termination & SSE/WS Proxy   |
|  - Port 8443: Bundler SSL Proxy               |
+-----------------------+-----------------------+
                        |
       +----------------+----------------+
       | (Port 3080)                     | (Port 80)
       v                                 v
+-------------------+           +-------------------+
|  LibreChat 本体   |           | Sandpack Bundler  |
+-------------------+           +-------------------+
```

---

## 3. SSL 証明書の生成 (`certs/generate_cert.sh`)

ホスト IP アドレス（例: `192.168.1.100`）および `localhost`, `127.0.0.1` を SAN（Subject Alternative Name）に含めた自己署名証明書をワンコマンドで生成できます：

```bash
bash certs/generate_cert.sh
```

---

## 4. 正式な CA 証明書（商用 / 社内 PKI / Let's Encrypt）への入れ替え手順

本番運用や社内正式展開において、信頼された認証局（CA）から発行された正式な SSL/TLS 証明書へ切り替える手順です。

### 4.1 証明書ファイルの準備と配置
Nginx コンテナは `./certs` ディレクトリを読み取り専用マウントしているため、正式な証明書と秘密鍵を以下のファイル名で配置します。

| ファイル名 | 内容 | 備考 |
| :--- | :--- | :--- |
| **`certs/server.crt`** | **サーバ証明書 + 中間CA証明書 (フルチェーン)** | 中間CA証明書がある場合は、サーバ証明書の後ろに結合して配置します。 |
| **`certs/server.key`** | **秘密鍵 (Private Key)** | パスフレーズなしの RSA / ECDSA 秘密鍵。 |

```bash
# 1. 既存の自己署名証明書のバックアップ（任意）
mv certs/server.crt certs/server.crt.selfsigned
mv certs/server.key certs/server.key.selfsigned

# 2. 正式な証明書と秘密鍵を配置
cp /path/to/your_domain.fullchain.crt certs/server.crt
cp /path/to/your_domain.key certs/server.key

# 3. 適切なパーミッションを設定
chmod 644 certs/server.crt
chmod 600 certs/server.key
```

### 4.2 証明書と秘密鍵の整合性確認 (事前チェック)
適用前に、証明書と秘密鍵のペアが一致しているか（モジュラスのハッシュ値が同一か）を確認します：

```bash
# 証明書のモジュラス確認
openssl x509 -noout -modulus -in certs/server.crt | openssl md5

# 秘密鍵のモジュラス確認
openssl rsa -noout -modulus -in certs/server.key | openssl md5

# ※ 両方の出力（MD5 ハッシュ値）が完全に一致していれば正常です。
```

### 4.3 Nginx の設定再読み込み（無停止切り替え）
コンテナを停止・再起動することなく、数ミリ秒の無停止で新しい証明書を反映できます：

```bash
# Nginx 設定テスト
docker exec librechat-nginx nginx -t

# 設定と証明書のホットリロード
docker exec librechat-nginx nginx -s reload
```

---

### 4.4 シナリオ別 運用ガイド

#### シナリオ A: Let's Encrypt / Certbot を利用する場合
パブリックドメイン（例: `chat.example.com`）をお持ちの場合、Certbot 等で自動取得した証明書をシンボリックリンクまたはコピーして配置します。

```bash
# 例: Certbot で取得した場合
sudo cp /etc/letsencrypt/live/chat.example.com/fullchain.pem ./certs/server.crt
sudo cp /etc/letsencrypt/live/chat.example.com/privkey.pem ./certs/server.key
sudo chown $(id -u):$(id -g) ./certs/server.*
docker exec librechat-nginx nginx -s reload
```

#### シナリオ B: 社内プライベート CA / Active Directory 認証局 (AD CS) を利用する場合
社内イントラネット専用のドメイン（例: `librechat.corp.local`）や IP 向けに社内 CA から発行された証明書を適用します。
1. CSR を作成して社内 CA に提出・発行を受ける。
2. サーバ証明書と社内中間 CA 証明書を結合して `server.crt` とする：
   ```bash
   cat server_cert.pem intermediate_ca.pem > certs/server.crt
   ```
3. クライアント端末（Windows / Mac / Linux）側にあらかじめ社内ルート CA 証明書が配布されていれば、ブラウザの警告なしで安全に接続できます。

---

## 5. 将来の OIDC / SSO 拡張方針

本アーキテクチャでは、要件やセキュリティポリシーに応じて以下の **2つのアプローチ** で OIDC / SSO を実現できます。

### パターン 1: LibreChat 内蔵 OIDC / OAuth2 の利用（推奨・標準）
LibreChat はネイティブで OpenID Connect (OIDC) 認証機能を内蔵しているため、**Nginx 側への追加コンテナ（oauth2-proxy 等）を挟まずに** SSO 連携が可能です。

* **役割分担**:
  * **Nginx**: SSL 終端と標準的なプロキシヘッダー（`X-Forwarded-Proto`, `Host` 等）の転送のみを担当（現在の構成のまま）。
  * **LibreChat**: IdP（Keycloak, Microsoft Entra ID, Google 等）とのトークン検証およびユーザーの自動プロビジョニング・セッション管理を担当。
* **設定方法**:
  LibreChat 本体の `.env` に OIDC 関連環境変数（`OPENID_CLIENT_ID`, `OPENID_ISSUER`, `OPENID_SESSION_SECRET` 等）を設定するだけで完結します。

---

### パターン 2: oauth2-proxy + Nginx によるネットワーク前段認証
LibreChat アプリケーションの手前（ネットワーク層）で厳密にアクセス制限・IP フィルタリングをかけたい場合に採用します。

* **構成**:
  1. **oauth2-proxy の導入**: Nginx の `auth_request` ディレクティブを用い、LibreChat へのパケット到達前に IdP での認証を強制。
  2. **ヘッダーベース SSO**: 認証済みユーザー情報（メールアドレス・表示名）を `X-Forwarded-User` 等のヘッダーで LibreChat へ伝達。
  

