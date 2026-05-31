# -*- coding: utf-8 -*-
import os
import yaml
import re

# パス定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKER_COMPOSE_PATH = os.path.join(BASE_DIR, "docker-compose.librechat.yml")
ENV_LIBRECHAT_PATH = os.path.join(BASE_DIR, ".env.librechat")
ENV_PATH = os.path.join(BASE_DIR, ".env")

def test_docker_compose_sandpack_bundler_profile():
    """
    docker-compose.librechat.yml 内の sandpack-bundler サービスが
    'ssl-mode' プロファイルで定義されており、コメントアウトされていないことを検証します。
    """
    assert os.path.exists(DOCKER_COMPOSE_PATH), f"{DOCKER_COMPOSE_PATH} が存在しません。"
    
    with open(DOCKER_COMPOSE_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    services = config.get("services", {})
    assert "sandpack-bundler" in services, "sandpack-bundler サービスが定義されていません（コメントアウトされたままの可能性があります）。"
    
    bundler_service = services["sandpack-bundler"]
    profiles = bundler_service.get("profiles", [])
    
    assert "ssl-mode" in profiles, "sandpack-bundler サービスに 'ssl-mode' プロファイルが設定されていません。"

def test_env_librechat_sandpack_bundler_url_phase1():
    """
    .env.librechat 内の SANDPACK_BUNDLER_URL がフェーズ1の要件に従って、
    空値またはコメントアウトされていることを検証します。
    また、フェーズ1およびフェーズ2・3の説明文が含まれていることを検証します。
    """
    assert os.path.exists(ENV_LIBRECHAT_PATH), f"{ENV_LIBRECHAT_PATH} が存在しません。"
    
    with open(ENV_LIBRECHAT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 説明文の検証
    assert "【フェーズ1: 非SSL環境 (デフォルト)】" in content, "フェーズ1の説明が .env.librechat に含まれていません。"
    assert "【フェーズ2: 自己署名SSLテスト環境】" in content, "フェーズ2の説明が .env.librechat に含まれていません。"
    assert "【フェーズ3: オンプレミス本番/社内CA証明書の適用】" in content, "フェーズ3の説明が .env.librechat に含まれていません。"
    
    # SANDPACK_BUNDLER_URL の設定が有効化されていないことを検証
    # 有効な行（コメントアウトされていない行）で SANDPACK_BUNDLER_URL に値が設定されているか確認
    lines = content.splitlines()
    active_value = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("SANDPACK_BUNDLER_URL") and "=" in stripped:
            parts = stripped.split("=", 1)
            active_value = parts[1].strip()
            
    # フェーズ1では、アクティブな SANDPACK_BUNDLER_URL は空または未定義である必要があります。
    assert active_value is None or active_value == "", f"アクティブな SANDPACK_BUNDLER_URL が設定されています: '{active_value}'。フェーズ1では空値であるか、コメントアウトされている必要があります。"
