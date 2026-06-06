# -*- coding: utf-8 -*-
import os
import yaml

# パス定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKER_COMPOSE_PATH = os.path.join(BASE_DIR, "docker-compose.librechat.yml")
CADDYFILE_PATH = os.path.join(BASE_DIR, "Caddyfile")

def test_caddyfile_exists_and_configured():
    """
    Caddyfile が存在し、LibreChat本体(443)とSandpack Bundler(8443)のリバースプロキシ設定が
    tls internal (自己署名) 付きで正しく構成されているかを検証します。
    """
    assert os.path.exists(CADDYFILE_PATH), "Caddyfile がプロジェクトルートに存在しません。"
    
    with open(CADDYFILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    # blue-two.local:443 と tls internal の設定確認
    assert "blue-two.local:443" in content, "Caddyfile に blue-two.local:443 の定義がありません。"
    assert "reverse_proxy librechat:3080" in content, "Caddyfile に librechat:3080 へのリバースプロキシ設定がありません。"
    
    # blue-two.local:8443 と tls internal の設定確認
    assert "blue-two.local:8443" in content, "Caddyfile に blue-two.local:8443 の定義がありません。"
    assert "reverse_proxy sandpack-bundler:80" in content, "Caddyfile に sandpack-bundler:80 へのリバースプロキシ設定がありません。"
    
    # tls 設定の存在確認 (自己署名、またはカスタムCAをサポートする形式)
    assert "tls internal" in content, "Caddyfile 内にデフォルトの 'tls internal' 設定がありません。"

def test_docker_compose_caddy_service():
    """
    docker-compose.librechat.yml 内に caddy サービスが定義され、
    'ssl-mode' プロファイルで、ポート443と8443がマッピングされていることを検証します。
    """
    assert os.path.exists(DOCKER_COMPOSE_PATH)
    
    with open(DOCKER_COMPOSE_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    services = config.get("services", {})
    assert "caddy" in services, "docker-compose.librechat.yml に caddy サービスが定義されていません。"
    
    caddy_service = services["caddy"]
    
    # profiles に ssl-mode が含まれているか確認
    profiles = caddy_service.get("profiles", [])
    assert "ssl-mode" in profiles, "caddy サービスに 'ssl-mode' プロファイルが設定されていません。"
    
    # ports の確認
    ports = caddy_service.get("ports", [])
    # Environment variable interpolation support (default values 443 and 8443)
    # We check for the specific mappings with optional env var syntax
    assert any(p == "443:443" or p == "${CADDY_HTTPS_PORT:-443}:443" for p in ports), "caddy サービスのポートに '443:443' (または変形式) が設定されていません。"
    assert any(p == "8443:8443" or p == "${CADDY_SANDPACK_PORT:-8443}:8443" for p in ports), "caddy サービスのポートに '8443:8443' (または変形式) が設定されていません。"
    
    # volumes の確認
    volumes = caddy_service.get("volumes", [])
    has_caddyfile_mount = False
    has_data_volume = False
    has_config_volume = False
    for vol in volumes:
        if "./Caddyfile:/etc/caddy/Caddyfile" in vol:
            has_caddyfile_mount = True
        if "caddy-data:/data" in vol:
            has_data_volume = True
        if "caddy-config:/config" in vol:
            has_config_volume = True
            
    assert has_caddyfile_mount, "Caddyfile のマウント設定が見つかりません。"
    assert has_data_volume, "caddy-data ボリュームのマウント設定が見つかりません。"
    assert has_config_volume, "caddy-config ボリュームのマウント設定が見つかりません。"

def test_docker_compose_volumes_definition():
    """
    docker-compose.librechat.yml の最下部に caddy-data および caddy-config
    のボリューム定義があることを検証します。
    """
    assert os.path.exists(DOCKER_COMPOSE_PATH)
    
    with open(DOCKER_COMPOSE_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    volumes = config.get("volumes", {})
    assert "caddy-data" in volumes, "docker-compose.librechat.yml の volumes に caddy-data が定義されていません。"
    assert "caddy-config" in volumes, "docker-compose.librechat.yml の volumes に caddy-config が定義されていません。"
