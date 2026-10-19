"""The release entry must compose the same dataset routes as source/dev."""
def test_engine_entry_selects_composed_dataset_app(tmp_path, monkeypatch):
    import backend.__main__ as entry
    import backend.engine as engine
    import backend.logging_config as logging
    from fastapi.testclient import TestClient

    observed = []

    def inspect(server):
        with TestClient(server.config.app) as client:
            assert client.get("/health").status_code == 200
            client.headers["Authorization"] = "Bearer " + server.identity.token
            response = client.post("/api/v1/datasets/import", json={"path": str(tmp_path / "absent.hdr")})
            assert response.status_code == 400 and response.json()["error"] == "FILE_NOT_FOUND"
            observed.append(True)

    monkeypatch.setattr(logging, "configure_logging", lambda _: None)
    monkeypatch.setattr(engine.HandshakeServer, "run", inspect)
    assert entry.main(["--data-root", str(tmp_path)]) == 0
    assert observed == [True]


def test_data_root_override_keeps_default_protocol_and_selects_explicit_root(tmp_path, monkeypatch):
    import backend.__main__ as entry
    import backend.engine as engine
    import backend.logging_config as logging
    from backend import __version__

    roots = []
    monkeypatch.setattr(logging, "configure_logging", lambda _: None)
    monkeypatch.setattr(engine, "main", lambda paths: roots.append(paths.root))
    assert entry.main(["--data-root", str(tmp_path)]) == 0
    assert roots == [tmp_path]
    assert __version__ == "0.1.0"


def test_relative_data_root_is_rejected_before_logging(monkeypatch, capsys):
    import backend.__main__ as entry
    import backend.logging_config as logging

    def forbidden(_):
        raise AssertionError("invalid path must not initialize logs")

    monkeypatch.setattr(logging, "configure_logging", forbidden)
    assert entry.main(["--data-root", "relative"]) == 2
    assert "绝对路径" in capsys.readouterr().err
