from app.config import Settings


def test_settings_reads_mz_bootstrap_token(monkeypatch) -> None:
    monkeypatch.delenv("BOOTSTRAP_TOKEN", raising=False)
    monkeypatch.setenv("MZ_BOOTSTRAP_TOKEN", "bootstrap-contract-token")

    settings = Settings(_env_file=None)

    assert settings.bootstrap_token == "bootstrap-contract-token"
