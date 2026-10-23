from clawback import config, llm
from clawback.tools import tavily


def test_load_env_file_reads_key(tmp_path, monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    (tmp_path / ".env").write_text("NEBIUS_API_KEY=abc123\n")
    config.load_env_file(tmp_path / ".env")
    assert config.Settings().nebius_api_key == "abc123"


def test_load_env_file_does_not_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "from-shell")
    (tmp_path / ".env").write_text("NEBIUS_API_KEY=from-file\n")
    config.load_env_file(tmp_path / ".env")
    assert config.Settings().nebius_api_key == "from-shell"


def test_tests_are_offline():
    assert llm.available() is False and tavily.available() is False
