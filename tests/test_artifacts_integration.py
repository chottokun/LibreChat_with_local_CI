# -*- coding: utf-8 -*-
import os
import subprocess
import yaml

# パス定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKER_COMPOSE_MAIN = os.path.join(BASE_DIR, "docker-compose.yml")
DOCKER_COMPOSE_LIBRECHAT = os.path.join(BASE_DIR, "docker-compose.librechat.yml")

def run_compose_config(profiles=None):
    """
    docker compose config コマンドを実行し、パースされた辞書オブジェクトを返します。
    """
    cmd = ["docker", "compose", "-f", DOCKER_COMPOSE_MAIN, "-f", DOCKER_COMPOSE_LIBRECHAT]
    if profiles:
        for profile in profiles:
            cmd.extend(["--profile", profile])
    cmd.append("config")
    
    # 環境変数を継承しつつ、ダミーのAPIキーなどを設定してconfig検証が通るようにする
    env = os.environ.copy()
    if "LIBRECHAT_CODE_API_KEY" not in env:
        env["LIBRECHAT_CODE_API_KEY"] = "dummy_key_for_integration_testing"
        
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=BASE_DIR)
    assert result.returncode == 0, f"docker compose config が失敗しました。\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    
    return yaml.safe_load(result.stdout)

def test_integration_docker_compose_syntax():
    """
    B-3: docker compose config がエラーなく実行でき、YAMLの構文やボリューム、
    環境変数の参照が有効であることを検証します。
    """
    config = run_compose_config()
    assert config is not None
    assert "services" in config

def test_integration_phase1_profile_behavior():
    """
    B-1: 通常起動（プロファイル指定なし）時、
    sandpack-bundler および nginx サービスが構成から除外される（休止される）ことを検証します。
    """
    config = run_compose_config()
    services = config.get("services", {})
    
    # フェーズ1では、プロファイル指定なしで起動した場合、
    # 'sandpack-bundler' と 'nginx' コンテナは起動してはならない（構成に含まれない）
    assert "sandpack-bundler" not in services, "フェーズ1（通常起動）であるにもかかわらず、sandpack-bundler が構成に含まれています。"
    assert "nginx" not in services, "フェーズ1（通常起動）であるにもかかわらず、nginx が構成に含まれています。"

def test_integration_phase2_profile_behavior():
    """
    B-2: ssl-mode プロファイル指定時、
    sandpack-bundler および nginx サービスが構成に正しく含まれる（起動される）ことを検証します。
    """
    config = run_compose_config(profiles=["ssl-mode"])
    services = config.get("services", {})
    
    # フェーズ2・3（ssl-mode）では、両方のサービスが含まれている必要がある
    assert "sandpack-bundler" in services, "ssl-mode プロファイルが指定されたが、sandpack-bundler が構成に含まれていません。"
    assert "nginx" in services, "ssl-mode プロファイルが指定されたが、nginx が構成に含まれていません。"
    
    # 依存関係（depends_on）のチェック
    nginx_service = services["nginx"]
    depends_on = nginx_service.get("depends_on", {})
    
    # docker compose config のバージョンによっては depends_on がリストまたは辞書になるため柔軟に対応
    depends_list = list(depends_on.keys()) if isinstance(depends_on, dict) else list(depends_on)
    assert "librechat" in depends_list, "nginx の起動依存関係に librechat がありません。"
    assert "sandpack-bundler" in depends_list, "nginx の起動依存関係に sandpack-bundler がありません。"

