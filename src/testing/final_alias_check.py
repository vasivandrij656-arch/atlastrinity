"""Final verification of aliases via Vibe implementation"""

import os
import subprocess
import time

import requests

# os.chdir(os.getcwd())


def test_alias(alias, prompt):

    # We must use VIBE_HOME with our config
    # For this test, we assume the config is already synced to ~/.config/atlastrinity/vibe_config.toml
    # But Vibe CLI uses ~/.vibe/config.toml or local .vibe/config.toml
    # Let's ensure we use the global one or just set the alias in the active config.

    # Actually, simpler: we create a temp config for each test like before
    vibe_home = f"/tmp/vibe_test_{alias}"
    os.makedirs(vibe_home, exist_ok=True)

    # Read main template
    with open("config/vibe_config.toml.template") as f:
        config = f.read()

    # We don't need to change models since they are already in the template with correct aliases!
    # We just need to set active_model
    import re

    config = re.sub(r'active_model = ".*"', f'active_model = "{alias}"', config)

    # Disable MCP for speed/reliability in this specific test
    config = re.sub(r"\[\[mcp_servers\]\].*", "", config, flags=re.DOTALL)

    with open(f"{vibe_home}/config.toml", "w") as f:
        f.write(config)

    env = os.environ.copy()
    env["VIBE_HOME"] = vibe_home
    env["COPILOT_SESSION_TOKEN"] = "dummy_token_will_be_fetched_by_proxy_script_logic"
    # Actually we need real token for proxy to work, BUT the proxy script handles it.
    # The vibe CLI just sends request to localhost:8085

    # Start proxy if not running? No, we will start it in main

    result = subprocess.run(
        ["vibe", "-p", prompt, "--output", "text"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    return result.returncode == 0


# 1. Start Proxy
# Fetch real token first for the proxy process (simulating what the server does)
# We can just run the proxy script, it fetches token internally? No, it expects COPILOT_SESSION_TOKEN
# provided by the caller (vibe_server.py usually does this).
# So we need to fetch it.

headers = {
    "Authorization": f"token {os.getenv('COPILOT_API_KEY')}",
    "Editor-Version": "vscode/1.85.0",
    "Editor-Plugin-Version": "copilot/1.144.0",
    "User-Agent": "GithubCopilot/1.144.0",
}
resp = requests.get("https://api.github.com/copilot_internal/v2/token", headers=headers)
token = resp.json().get("token")

proxy_proc = subprocess.Popen(
    ["python3", "src/providers/proxy/copilot_vibe_proxy.py"],
    env={**os.environ, "COPILOT_SESSION_TOKEN": token},
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
time.sleep(3)  # Wait for startup

try:
    test_alias("raptor-mini", "Calculate 12 * 7")
    test_alias("grok-code-fast-1", "Write a python hello world")
    test_alias("gpt-4.1", "Explain quantum computing briefly")
finally:
    proxy_proc.terminate()
