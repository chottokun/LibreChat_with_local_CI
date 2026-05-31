# -*- coding: utf-8 -*-
import os
import yaml

# パス定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKER_COMPOSE_PATH = os.path.join(BASE_DIR, "docker-compose.librechat.yml")
CADDYFILE_PATH = os.path.join(BASE_DIR, "Caddyfile")
ENV_LIBRECHAT_PATH = os.path.join(BASE_DIR, ".env.librechat")

def test_onprem_caddyfile_hybrid_tls():
    """
    Caddyfile 内に自己署名証明書（tls internal）のデフォルト設定と、
    マウントされたカスタム証明書（tls /certs/librechat.crt ...）の切替設定が存在することを検証します。
    """
    assert os.path.exists(CADDYFILE_PATH), "Caddyfile が存在しません。"
    
    with open(CADDYFILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    # デフォルトの tls internal 指定が存在することを確認
    assert "tls internal" in content, "Caddyfile 内にデフォルトの 'tls internal' 設定がありません。"
    # カスタム証明書用のパス指定が存在することを確認（コメントアウト状態を含む）
    assert "tls /certs/librechat.crt /certs/librechat.key" in content, "Caddyfile 内にカスタム証明書適用のプレースホルダーがありません。"

def test_onprem_docker_compose_caddy_mounts_and_envs():
    """
    docker-compose.librechat.yml 内の caddy サービスに、
    オンプレミス用のカスタム証明書環境変数および読み取り専用マウント（./certs:/certs:ro）
    が定義されていることを検証します。
    """
    assert os.path.exists(DOCKER_COMPOSE_PATH)
    
    with open(DOCKER_COMPOSE_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    services = config.get("services", {})
    assert "caddy" in services, "caddy サービスが定義されていません。"
    
    caddy_service = services["caddy"]
    
    # 環境変数の確認
    environments = caddy_service.get("environment", [])
    has_cert_env = False
    has_key_env = False
    for env in environments:
        if "CUSTOM_CERT_PATH=" in env:
            has_cert_env = True
        if "CUSTOM_KEY_PATH=" in env:
            has_key_env = True
            
    assert has_cert_env, "caddy サービスの環境変数に CUSTOM_CERT_PATH が定義されていません。"
    assert has_key_env, "caddy サービスの環境変数に CUSTOM_KEY_PATH が定義されていません。"
    
    # ボリュームマウントの確認
    volumes = caddy_service.get("volumes", [])
    has_certs_mount = False
    for vol in volumes:
        if "./certs:/certs:ro" in vol:
            has_certs_mount = True
            
    assert has_certs_mount, "caddy サービスのボリュームに './certs:/certs:ro' のマウント定義がありません。"

def test_onprem_env_librechat_templates():
    """
    .env.librechat テンプレートにオンプレミス（フェーズ3）用の
    CUSTOM_CERT_PATH および CUSTOM_KEY_PATH の設定プレースホルダーが含まれていることを検証します。
    """
    assert os.path.exists(ENV_LIBRECHAT_PATH)
    
    with open(ENV_LIBRECHAT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "CUSTOM_CERT_PATH=" in content, ".env.librechat に CUSTOM_CERT_PATH の記述がありません。"
    assert "CUSTOM_KEY_PATH=" in content, ".env.librechat に CUSTOM_KEY_PATH の記述がありません。"
    assert "【フェーズ3: オンプレミス本番/社内CA証明書の適用】" in content, ".env.librechat にオンプレミスフェーズ3用の説明がありません。"
