---
type: Concept
title: Reverse Proxy & SSL Design (Nginx)
description: Nginx を用いた SSL/TLS 終端、SAN 証明書、WebSocket/SSE リアルタイムストリーミング、将来の OIDC/SSO 連携設計
status: active
timestamp: 2026-08-14T11:00:00+09:00
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
1. **SSL/TLS 終端**: IP アドレス直接アクセス（例: `https://192.168.1.100`）およびローカルホスト（`https://localhost`）での安全な暗号化通信。
2. **リアルタイムストリーミング**: AI の文字生成（Server-Sent Events: SSE）および WebSocket の低遅延中継（`proxy_buffering off`）。
3. **Artifacts (Sandpack Bundler) 連携**: ポート 8443 による React/HTML 等の UI 描画コンテナの HTTPS 化。
4. **将来の OIDC / SSO 拡張性**: Keycloak、Entra ID (Azure AD)、Google Workspace 等との連携基盤。

---

## 2. アーキテクチャ構成

```
[ ブラウザ / クライアント (LAN / Local) ]
        |
        | HTTPS (Port 443) / HTTPS (Port 8443)
        v
+-----------------------------------------------+
|         Nginx (Reverse Proxy Container)       |
|  - SSL Termination (server.crt / server.key)  |
|  - WebSocket / SSE Proxying                   |
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

## 4. 将来の OIDC / SSO 拡張方針

Nginx をフロントに配置することで、以下のエンタープライズ認証拡張が容易に実現可能です：
1. **`oauth2-proxy` の導入**:
   - Nginx の `auth_request` ディレクティブを用い、LibreChat へのアクセス前に OIDC 認証（IDプロバイダ認証）を要求。
2. **ヘッダーベースのシングルサインオン (SSO)**:
   - 認証済みユーザー情報（メールアドレス・表示名）を `X-Forwarded-User` 等のヘッダーで安全に LibreChat 側へ伝達。
