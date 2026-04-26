from gw import __main__ as package_main


def test_package_entrypoint_delegates_to_web_main(monkeypatch):
    calls = []

    monkeypatch.setattr(
        package_main,
        "web_main",
        lambda argv: calls.append(argv),
    )

    package_main.main(["--config", "config.yaml"])

    assert calls == [["--config", "config.yaml"]]
