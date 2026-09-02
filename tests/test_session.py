from app.core.session import SessionStore, State


def test_state_order_and_terminal_state():
    store = SessionStore()
    s = store.create()
    assert s.state == State.GREET
    seen = [s.state]
    for _ in range(5):
        seen.append(s.advance())
    assert seen == [
        State.GREET,
        State.IDENTIFY,
        State.CHECKLIST,
        State.SCAN,
        State.FILL,
        State.DELIVER,
    ]
    assert s.advance() == State.DELIVER  # cannot advance past the final state


def test_new_session_loads_editable_sample_profile():
    store = SessionStore()
    s = store.create()
    assert s.profile.name == "Demo Citizen"
    assert s.profile.state == "Goa"
    assert s.profile.occupation == "student"


def test_restart_service_returns_to_identify():
    store = SessionStore()
    s = store.create()
    for _ in range(5):
        s.advance()
    s.restart_service()
    assert s.state == State.IDENTIFY
    assert s.service_id is None


def test_wipe_removes_session_and_artifacts(tmp_path):
    store = SessionStore()
    s = store.create()
    f = tmp_path / "scan.png"
    f.write_text("x")
    s.artifacts.append(str(f))
    store.wipe(s.id)
    assert store.get(s.id) is None
    assert not f.exists()
