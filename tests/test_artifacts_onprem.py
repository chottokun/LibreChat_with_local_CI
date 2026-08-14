# -*- coding: utf-8 -*-
import os
import yaml

# パス定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKER_COMPOSE_PATH = os.path.join(BASE_DIR, "docker-compose.librechat.yml")
GENERATE_CERT_SCRIPT = os.path.join(BASE_DIR, "certs", "generate_cert.sh")
ENV_LIBRECHAT_PATH = os.path.join(BASE_DIR, ".env.librechat")

def test_onprem_generate_cert_script():
    """
    SAN (Subject Alternative Name) 付き証明書生成スクリプトが存在し、
    ホストIPおよびlocalhostをカバーする構成になっていることを検証します。
    """
    assert os.path.exists(GENERATE_CERT_SCRIPT), "generate_cert.sh が存在しません。"
    
    with open(GENERATE_CERT_SCRIPT, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "subjectAltName" in content, "generate_cert.sh に SAN (subjectAltName) の定義がありません。"
    assert "server.crt" in content and "server.key" in content, "generate_cert.sh に server.crt/key 出力設定がありません。"

def test_onprem_docker_compose_nginx_mounts():
    """
    docker-compose.librechat.yml 内の nginx サービスに、
    証明書マウント（./certs:/etc/nginx/certs:ro）が定義されていることを検証します。
    """
    assert os.path.exists(DOCKER_COMPOSE_PATH)
    
    with open(DOCKER_COMPOSE_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    services = config.get("services", {})
    assert "nginx" in services, "nginx サービスが定義されていません。"
    
    nginx_service = services["nginx"]
    
    # ボリュームマウントの確認
    volumes = nginx_service.get("volumes", [])
    has_certs_mount = False
    for vol in volumes:
        if "./certs:/etc/nginx/certs:ro" in vol:
            has_certs_mount = True
            
    assert has_certs_mount, "nginx サービスのボリュームに './certs:/etc/nginx/certs:ro' のマウント定義がありません。"

def test_onprem_env_librechat_templates():
    """
    .env.librechat テンプレートに HTTPS ポート設定およびオンプレミス用の説明が含まれていることを検証します。
    """
    assert os.path.exists(ENV_LIBRECHAT_PATH)
    
    with open(ENV_LIBRECHAT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "HTTP_PORT=" in content, ".env.librechat に HTTP_PORT の記述がありません。"
    assert "HTTPS_PORT=" in content, ".env.librechat に HTTPS_PORT の記述がありません。"
    assert "SANDPACK_HTTPS_PORT=" in content, ".env.librechat に SANDPACK_HTTPS_PORT の記述がありません。"
    assert "【フェーズ3: オンプレミス本番/社内CA証明書の適用】" in content, ".env.librechat にオンプレミスフェーズ3用の説明がありません。"
