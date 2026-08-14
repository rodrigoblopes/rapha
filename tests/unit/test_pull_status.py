"""Pull freshness maths, the marker round-trip, and the launch command. No sockets."""

from __future__ import annotations

from types import SimpleNamespace

from rapha import pull_status


def test_record_then_read_round_trips(tmp_path):
    pull_status.record_pull(tmp_path, {"activities": 100, "weigh_ins": 15})
    got = pull_status.read_last_pull(tmp_path)
    assert got["summary"] == {"activities": 100, "weigh_ins": 15}
    assert got["epoch"] > 0 and "at" in got


def test_read_is_none_when_never_pulled(tmp_path):
    assert pull_status.read_last_pull(tmp_path) is None


def test_a_recent_pull_is_fresh(tmp_path):
    pull_status.record_pull(tmp_path, {})
    epoch = pull_status.read_last_pull(tmp_path)["epoch"]
    st = pull_status.pull_status(tmp_path, now_epoch=epoch + 600, check_chrome=False)
    assert st["fresh"] is True
    assert st["age_seconds"] == 600
    assert st["chrome_up"] is None  # skipped


def test_an_old_pull_is_stale(tmp_path):
    pull_status.record_pull(tmp_path, {})
    epoch = pull_status.read_last_pull(tmp_path)["epoch"]
    st = pull_status.pull_status(tmp_path, now_epoch=epoch + 3601, check_chrome=False)
    assert st["fresh"] is False
    assert st["age_seconds"] == 3601


def test_never_pulled_is_not_fresh(tmp_path):
    st = pull_status.pull_status(tmp_path, now_epoch=1_000_000, check_chrome=False)
    assert st["fresh"] is False
    assert st["age_seconds"] is None
    assert st["last_pull_at"] is None


def test_freshness_threshold_is_configurable(tmp_path):
    pull_status.record_pull(tmp_path, {})
    epoch = pull_status.read_last_pull(tmp_path)["epoch"]
    # 30 minutes old, threshold 15 -> stale
    st = pull_status.pull_status(tmp_path, now_epoch=epoch + 1800,
                                 fresh_minutes=15, check_chrome=False)
    assert st["fresh"] is False


def test_launch_command_is_fixed_and_debuggable(tmp_path):
    cmd = pull_status.launch_command(r"C:\chrome.exe", str(tmp_path / "prof"))
    assert cmd[0] == r"C:\chrome.exe"
    assert "--remote-debugging-port=9222" in cmd
    assert any(a.startswith("--user-data-dir=") for a in cmd)
    assert cmd[-1] == pull_status.GARMIN_SIGNIN  # lands on the login page


def test_chrome_up_is_false_on_a_dead_port():
    # Nothing listens on this port in the test environment.
    assert pull_status.chrome_debug_up(port=59999, timeout=0.2) is False


def test_corrupt_marker_reads_as_none(tmp_path):
    (tmp_path / "data" / "cache").mkdir(parents=True)
    (tmp_path / "data" / "cache" / "last_pull.json").write_text("{ not json",
                                                                encoding="utf-8")
    assert pull_status.read_last_pull(tmp_path) is None


def test_endpoint_status_from_a_fake_config(tmp_path):
    # what GET /pull-status serves, without the socket check
    pull_status.record_pull(tmp_path, {"days": 45})
    cfg = SimpleNamespace(home=tmp_path)
    st = pull_status.pull_status(cfg.home, check_chrome=False)
    assert st["summary"] == {"days": 45}
