import app.main as main


def test_chrome_launch_preserves_portal_query_string(monkeypatch, tmp_path):
    portal_url = (
        "https://goaonline.gov.in/Appln/UIL/deptServices"
        "?__DocId=REV&__ServiceId=REV07"
    )
    captured = {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "_chrome_executable", lambda: r"C:\Chrome\chrome.exe")
    monkeypatch.setattr(main, "_reuse_running_chrome", lambda url: False)

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

    monkeypatch.setattr(main.subprocess, "Popen", fake_popen)

    main._launch_chrome("test-session", portal_url)

    assert captured["command"][0] == r"C:\Chrome\chrome.exe"
    assert captured["command"][-1] == portal_url
    assert "cmd" not in captured["command"]
    assert captured["kwargs"]["shell"] is False


def test_chrome_launch_reuses_existing_logged_in_browser(monkeypatch):
    portal_url = (
        "https://goaonline.gov.in/Appln/UIL/deptServices"
        "?__DocId=REV&__ServiceId=REV07"
    )
    reused = []

    monkeypatch.setattr(main, "_reuse_running_chrome", lambda url: reused.append(url) or True)
    monkeypatch.setattr(
        main.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Chrome must be reused")),
    )

    main._launch_chrome("renewed-session", portal_url)

    assert reused == [portal_url]
