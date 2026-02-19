import sys

from providers.utils import get_copilot_token as gct


def test_main_auto_updates_env_by_default(monkeypatch):
    called = {}

    monkeypatch.setattr(gct, "get_token_oauth_device_flow", lambda: "ghu_dummy_token")
    monkeypatch.setattr(gct, "verify_token", lambda t: {"expires_at": 9999999999})

    def fake_update_all_env(token):
        called["token"] = token

    monkeypatch.setattr(gct, "update_all_env", fake_update_all_env)

    monkeypatch.setattr(sys, "argv", ["get_copilot_token.py", "--method", "vscode", "--quiet"])
    gct.main()

    assert called.get("token") == "ghu_dummy_token"


def test_main_respects_no_update_env_flag(monkeypatch):
    called = {"invoked": False}

    monkeypatch.setattr(gct, "get_token_oauth_device_flow", lambda: "ghu_dummy_token")
    monkeypatch.setattr(gct, "verify_token", lambda t: {"expires_at": 9999999999})

    def fake_update_all_env(token):
        called["invoked"] = True

    monkeypatch.setattr(gct, "update_all_env", fake_update_all_env)

    monkeypatch.setattr(
        sys, "argv", ["get_copilot_token.py", "--method", "vscode", "--no-update-env", "--quiet"]
    )
    gct.main()

    assert called["invoked"] is False
