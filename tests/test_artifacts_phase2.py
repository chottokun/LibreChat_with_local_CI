# -*- coding: utf-8 -*-
import os
import yaml

# パス定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKER_COMPOSE_PATH = os.path.join(BASE_DIR, "docker-compose.librechat.yml")
NGINX_CONF_PATH = os.path.join(BASE_DIR, "nginx.conf")

def test_nginx_conf_exists_and_configured():
    """
    nginx.conf が存在し、LibreChat本体(443)とSandpack Bundler(8443)のリバースプロキシ設定が
    SSL 証明書付きで正しく構成されているかを検証します。
    """
    assert os.path.exists(NGINX_CONF_PATH), "nginx.conf がプロジェクトルートに存在しません。"
    
    with open(NGINX_CONF_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    # ポート80 の HTTP -> HTTPS 301 リダイレクト設定確認
    assert "listen 80 default_server" in content, "nginx.conf に listen 80 default_server の定義がありません。"
    assert "return 301 https://$host$request_uri;" in content, "nginx.conf に HTTPS への 301 リダイレクト設定がありません。"
    
    # ポート443 と LibreChat リバースプロキシ設定確認
    assert "listen 443 ssl" in content, "nginx.conf に listen 443 ssl の定義がありません。"
    assert "proxy_pass http://librechat:3080;" in content, "nginx.conf に librechat:3080 へのリバースプロキシ設定がありません。"
    
    # ポート8443 と Sandpack Bundler 設定確認
    assert "listen 8443 ssl" in content, "nginx.conf に listen 8443 ssl の定義がありません。"
    assert "proxy_pass http://sandpack-bundler:80;" in content, "nginx.conf に sandpack-bundler:80 へのリバースプロキシ設定がありません。"
    
    # SSL 証明書設定およびストリーミングバッファ無効化設定の存在確認
    assert "ssl_certificate" in content, "nginx.conf に ssl_certificate 設定がありません。"
    assert "proxy_buffering off;" in content, "nginx.conf にリアルタイムSSE用の proxy_buffering off 設定がありません。"

def test_docker_compose_nginx_service():
    """
    docker-compose.librechat.yml 内に nginx サービスが定義され、
    'ssl-mode' プロファイルで、ポート80, 443と8443がマッピングされていることを検証します。
    """
    assert os.path.exists(DOCKER_COMPOSE_PATH)
    
    with open(DOCKER_COMPOSE_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    services = config.get("services", {})
    assert "nginx" in services, "docker-compose.librechat.yml に nginx サービスが定義されていません。"
    
    nginx_service = services["nginx"]
    
    # profiles に ssl-mode が含まれているか確認
    profiles = nginx_service.get("profiles", [])
    assert "ssl-mode" in profiles, "nginx サービスに 'ssl-mode' プロファイルが設定されていません。"
    
    # ports の確認
    ports = nginx_service.get("ports", [])
    assert any(p == "80:80" or "${HTTP_PORT:-80}:80" in p for p in ports), "nginx サービスのポートに 80 マッピングが設定されていません。"
    assert any(p == "443:443" or "${HTTPS_PORT:-443}:443" in p for p in ports), "nginx サービスのポートに 443 マッピングが設定されていません。"
    assert any(p == "8443:8443" or "${SANDPACK_HTTPS_PORT:-8443}:8443" in p for p in ports), "nginx サービスのポートに 8443 マッピングが設定されていません。"
    
    # volumes の確認
    volumes = nginx_service.get("volumes", [])
    has_nginx_conf_mount = False
    has_certs_mount = False
    for vol in volumes:
        if "./nginx.conf:/etc/nginx/nginx.conf:ro" in vol:
            has_nginx_conf_mount = True
        if "./certs:/etc/nginx/certs:ro" in vol:
            has_certs_mount = True
            
    assert has_nginx_conf_mount, "nginx.conf のマウント設定が見つかりません。"
    assert has_certs_mount, "certs ディレクトリのマウント設定が見つかりません。"
