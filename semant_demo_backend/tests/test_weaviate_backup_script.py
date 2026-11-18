"""deploy/weaviate_backup.py (#469): scheduled full and incremental backups, chain-aware
retention, the free-space refusal and ``check``, against a fake ``backup-filesystem`` Weaviate
that writes ``backup_config.json`` like Weaviate 1.40 does. The real-Weaviate part is in
tests/integration/test_weaviate_backup.py."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "weaviate_backup.py"
GIB = 1024 ** 3


def load_script():
    spec = importlib.util.spec_from_file_location("weaviate_backup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["weaviate_backup"] = module
    spec.loader.exec_module(module)
    return module


wb = load_script()


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


def write_backup(root: Path, backup_id: str, started: datetime, status="SUCCESS", base="", size=1000):
    directory = root / backup_id
    (directory / "node1").mkdir(parents=True, exist_ok=True)
    (directory / "node1" / "chunk-1").write_bytes(b"x" * size)
    (directory / wb.CONFIG_FILE).write_text(json.dumps({
        "id": backup_id, "status": status, "baseBackupId": base,
        "startedAt": started.strftime("%Y-%m-%dT%H:%M:%S.123456789Z"),
        "completedAt": (started + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.5Z"),
        "preCompressionSizeBytes": size * 2, "nodes": {}}))


class FakeWeaviate:
    """The backup API of ``backup-filesystem``: ``create`` writes the backup into ``root``
    with ``outcome`` (fast tests may not open sockets; the REST calls are covered by the
    integration test)."""

    def __init__(self, root: Path, clock: Clock):
        self.root, self.clock = root, clock
        self.outcome = "SUCCESS"
        self.write_to_disk = True
        self.created: list[dict] = []
        self.statuses: dict[str, str] = {}

    def create(self, backup_id, base=""):
        self.created.append({"id": backup_id, **({"incremental_base_backup_id": base} if base else {})})
        if base and not (self.root / base).is_dir():
            raise wb.BackupError(f"base {base} not found")
        self.statuses[backup_id] = self.outcome
        if self.write_to_disk:
            write_backup(self.root, backup_id, self.clock(), self.outcome, base)
        return {"id": backup_id, "status": "STARTED"}

    def status(self, backup_id):
        if backup_id not in self.statuses:
            raise wb.BackupError(f"GET /v1/backups/filesystem/{backup_id}: HTTP 404")
        return {"id": backup_id, "status": self.statuses[backup_id]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    root, state = tmp_path / "backups", tmp_path / "state"
    root.mkdir()
    clock = Clock()
    fake = FakeWeaviate(root, clock)
    monkeypatch.setattr(wb, "free_bytes", lambda path: 10_000 * GIB)

    class Env:
        pass

    e = Env()
    e.root, e.state, e.clock, e.fake = root, state, clock, fake
    e.environ = {"POLL_SECONDS": "0", "MIN_FREE_GIB": "1"}

    def run(*args, **extra):
        return wb.main([args[0], str(root), str(state), *args[1:]], {**e.environ, **extra},
                       clock=clock, sleep=lambda s: None, api=fake)

    e.run = run
    return e


def ids(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir())


def last_status(state: Path) -> str:
    return (state / "last_status").read_text()


# ── Full and incremental ──────────────────────────────────────────────────

def test_first_run_is_full_then_daily_incrementals_chain_on_the_previous_backup(env):
    assert env.run("backup") == 0
    env.clock.advance(days=1)
    assert env.run("backup") == 0
    env.clock.advance(days=1)
    assert env.run("backup") == 0

    full, incr1, incr2 = [c["id"] for c in env.fake.created]
    assert full == "auto-full-20261116-010000" and "incremental_base_backup_id" not in env.fake.created[0]
    assert env.fake.created[1]["incremental_base_backup_id"] == full
    assert env.fake.created[2]["incremental_base_backup_id"] == incr1
    assert f"OK id={incr2} kind=incr base={incr1} " in last_status(env.state)
    records = [json.loads(line) for line in (env.state / "manifest.jsonl").read_text().splitlines()]
    assert [(r["id"], r["base"], r["chain"], r["status"]) for r in records] == [
        (full, "", full, "SUCCESS"), (incr1, full, full, "SUCCESS"), (incr2, incr1, full, "SUCCESS")]
    assert all(r["disk_bytes"] > 0 for r in records)


def test_a_new_full_backup_after_the_interval_starts_a_new_chain(env):
    env.run("backup")
    env.clock.advance(days=6, hours=11)
    env.run("backup")
    # A daily run at the same time: the full backup started a fraction of a second after its run.
    env.clock.advance(hours=13)
    env.run("backup")

    kinds = [(c["id"].split("-")[1], c.get("incremental_base_backup_id")) for c in env.fake.created]
    assert kinds == [("full", None), ("incr", env.fake.created[0]["id"]), ("full", None)]


def test_a_failed_backup_is_recorded_never_used_as_base_and_deleted_later(env):
    env.run("backup")
    full = env.fake.created[0]["id"]
    env.clock.advance(days=1)
    env.fake.outcome = "FAILED"

    assert env.run("backup") == 1
    failed = env.fake.created[1]["id"]
    assert last_status(env.state).split(" ", 1)[1].startswith(f"FAILED: backup {failed} ended FAILED")
    assert env.run("check") == 1

    env.fake.outcome = "SUCCESS"
    env.clock.advance(hours=1)
    assert env.run("backup") == 0
    assert env.fake.created[2]["incremental_base_backup_id"] == full
    assert failed not in ids(env.root)


def test_a_backup_missing_from_the_backup_root_fails_the_run(env):
    env.fake.write_to_disk = False

    assert env.run("backup") == 1
    assert "holds no successful backup" in last_status(env.state)


# ── Retention ─────────────────────────────────────────────────────────────

def make_chains(env, chains: int, incrementals: int = 2) -> list[list[str]]:
    made = []
    for _ in range(chains):
        before = len(env.fake.created)
        for _ in range(incrementals + 1):
            assert env.run("backup") == 0
            env.clock.advance(days=1)
        env.clock.advance(days=7)
        made.append([c["id"] for c in env.fake.created[before:]])
    return made


def test_retention_keeps_the_newest_two_chains_and_deletes_older_ones_whole(env):
    write_backup(env.root, "backup-2026-11-16", env.clock() - timedelta(days=1))  # made by hand

    first, second, third = make_chains(env, 3)

    assert ids(env.root) == sorted(["backup-2026-11-16", *second, *third])
    deleted = [d for line in (env.state / "manifest.jsonl").read_text().splitlines()
               for d in json.loads(line)["deleted"]]
    assert deleted == sorted(first)


def test_retention_waits_until_the_new_full_backup_succeeded(env):
    first, second = make_chains(env, 2)
    env.fake.outcome = "FAILED"
    assert env.run("backup") == 1

    assert set(first + second) <= set(ids(env.root))


def test_a_kept_backup_protects_the_old_backups_it_depends_on(env):
    first, _second = make_chains(env, 2)
    # A backup made by hand on top of the old chain's last incremental keeps that whole chain.
    write_backup(env.root, "manual-on-old", env.clock(), base=first[-1])
    make_chains(env, 1)

    assert set(first) <= set(ids(env.root))
    assert "kept because another backup depends on them: " + " ".join(sorted(first)) in \
        _plan_output(env)


def _plan_output(env) -> str:
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert wb.main(["plan", str(env.root)], env.environ, clock=env.clock) == 0
    return out.getvalue()


def _full(i, status="SUCCESS"):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return wb.Backup(f"auto-full-2026010{i}-000000", status, "", t + timedelta(days=i), None)


def test_retention_deletes_failed_backups_but_never_backups_made_by_hand():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    backups = {b.id: b for b in [
        _full(1), _full(2), _full(3),
        wb.Backup("manual-incr", "SUCCESS", "auto-full-20260101-000000", t, None),
        wb.Backup("manual-old", "FAILED", "", t - timedelta(days=9), None),
        wb.Backup("auto-incr-20260102-120000", "FAILED", "auto-full-20260102-000000", t, None),
    ]}

    delete, protected, blockers = wb.retention(backups, keep_chains=2)

    # full 1 is outside the 2 kept chains, but a backup made by hand depends on it.
    assert delete == ["auto-incr-20260102-120000"]
    assert protected == ["auto-full-20260101-000000"]
    assert blockers == []


@pytest.mark.parametrize("status", ["STARTED", "TRANSFERRING", "UNKNOWN"])
def test_retention_deletes_nothing_while_a_backup_with_an_unknown_base_is_unsettled(status):
    # A manual incremental still running (or with unreadable metadata) may depend on the old chain.
    backups = {b.id: b for b in [
        _full(1), _full(2), _full(3), _full(4, status="FAILED"),
        wb.Backup("manual-running", status, "", None, None)]}

    assert wb.retention(backups, keep_chains=2) == ([], [], ["manual-running"])


def test_an_unfinished_manual_backup_blocks_retention_and_check_reports_it_when_stale(env, capsys):
    first, _second = make_chains(env, 2)
    running = env.root / "manual-incr-running"
    (running / "node1").mkdir(parents=True)  # no backup_config.json yet
    now = env.clock().timestamp()
    os.utime(running, (now, now))

    assert env.run("backup") == 0  # the third full backup: the first chain is now outside the 2 kept

    assert set(first) <= set(ids(env.root))
    assert "retention=skipped(manual-incr-running)" in last_status(env.state)
    assert env.run("check") == 0
    old = (env.clock() - timedelta(hours=21)).timestamp()
    os.utime(running, (old, old))
    capsys.readouterr()

    assert env.run("check") == 1
    assert "manual-incr-running has been unfinished or unreadable" in capsys.readouterr().err


def test_a_successful_incremental_on_a_broken_base_is_not_restorable(env, capsys):
    env.run("backup")
    env.clock.advance(days=1)
    env.run("backup")
    env.clock.advance(days=1)
    env.run("backup")
    full, incr1, incr2 = [c["id"] for c in env.fake.created]
    (env.root / incr1 / wb.CONFIG_FILE).write_text("{not json")  # corrupt intermediate base
    capsys.readouterr()

    assert env.run("check") == 1
    assert f"{incr2} cannot be restored: {incr1} in its chain is UNKNOWN" in capsys.readouterr().err
    assert f"{incr2}\tSUCCESS\tbase={incr1}\tchain=BROKEN" in _plan_output(env)
    # The next incremental is based on the last backup with a valid chain, not on incr2.
    env.clock.advance(days=1)
    assert env.run("backup") == 0
    assert env.fake.created[-1]["incremental_base_backup_id"] == full


def test_deletion_refuses_ids_not_made_by_the_script(tmp_path):
    (tmp_path / "manual").mkdir()
    with pytest.raises(wb.BackupError):
        wb.delete_backup(tmp_path, "manual")
    with pytest.raises(wb.BackupError):
        wb.delete_backup(tmp_path, "../auto-full-20260101-000000")


# ── Free space and mount ──────────────────────────────────────────────────

def test_a_backup_is_refused_when_the_pool_lacks_free_space(env, monkeypatch):
    monkeypatch.setattr(wb, "free_bytes", lambda path: 50 * GIB)

    assert env.run("backup", MIN_FREE_GIB="100") == 1

    assert env.fake.created == []
    assert "50 GiB free" in last_status(env.state) and "100 GiB required" in last_status(env.state)
    assert env.run("check") == 1


def test_the_required_space_scales_with_the_newest_full_backup(env, monkeypatch):
    write_backup(env.root, "backup-manual", env.clock() - timedelta(days=1), size=2_000_000)
    full_size = wb.disk_usage(env.root / "backup-manual")
    monkeypatch.setattr(wb, "free_bytes", lambda path: int(full_size * 1.1))

    assert env.run("backup", MIN_FREE_GIB="0", FREE_FACTOR="1.25") == 1
    assert env.fake.created == []
    assert env.run("backup", MIN_FREE_GIB="0", FREE_FACTOR="1.0") == 0


def test_backup_and_check_refuse_a_backup_mount_that_is_not_mounted(env, tmp_path):
    assert env.run("backup", BACKUP_MOUNT=str(tmp_path)) == 1
    assert env.fake.created == []
    assert env.run("check", BACKUP_MOUNT=str(tmp_path)) == 1


# ── check ─────────────────────────────────────────────────────────────────

def test_check_passes_after_a_successful_run_and_fails_when_stale(env, capsys):
    assert env.run("check") == 1  # no backups yet
    env.run("backup")
    assert env.run("check") == 0
    env.clock.advance(hours=27)

    assert env.run("check") == 1
    assert "older than 26 h" in capsys.readouterr().err


def test_check_fails_when_weaviate_does_not_report_the_backup_as_successful(env, capsys):
    env.run("backup")
    env.fake.statuses.clear()

    assert env.run("check") == 1
    assert "cannot read the status from Weaviate" in capsys.readouterr().err


def test_check_fails_when_the_last_run_did_not_record_ok_for_the_newest_backup(env):
    env.run("backup")
    (env.state / "last_status").write_text("2026-11-16T01:00:00Z RUNNING\n")

    assert env.run("check") == 1


# ── restore guard, times, settings ────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8080",      # production
    "http://10.0.0.5:8080",       # another address that may reach production
    "http://semant.example:8091",  # any endpoint not listed
])
def test_restore_accepts_only_listed_rehearsal_endpoints(url):
    endpoint = url.split("//")[1]
    with pytest.raises(wb.BackupError, match="not a rehearsal endpoint"):
        wb.run_restore("x", wb.Settings(), wb.Weaviate(url), endpoint, None)


def test_restore_requires_the_confirmed_endpoint_and_a_listed_one_cannot_be_production():
    with pytest.raises(wb.BackupError, match="does not match"):
        wb.run_restore("x", wb.Settings(), wb.Weaviate("http://127.0.0.1:8090"), "127.0.0.1:8091", None)
    listed = wb.Settings.from_env({"REHEARSAL_ENDPOINTS": "127.0.0.1:8080, 127.0.0.1:9000"})
    assert listed.rehearsal_endpoints == ("127.0.0.1:8080", "127.0.0.1:9000")
    with pytest.raises(wb.BackupError, match="not a rehearsal endpoint"):
        wb.run_restore("x", listed, wb.Weaviate("http://127.0.0.1:8080"), "127.0.0.1:8080", None)


class FakeRestoreApi:
    def __init__(self, url):
        self.url = url
        self.calls: list[tuple] = []
        self.polls = 0

    def restore(self, backup_id, include=None):
        self.calls.append((backup_id, include))
        return {"id": backup_id, "status": "STARTED"}

    def restore_status(self, backup_id):
        self.polls += 1
        return {"id": backup_id, "status": "SUCCESS" if self.polls > 1 else "TRANSFERRING"}


def test_restore_into_a_listed_rehearsal_endpoint_waits_for_the_restore():
    api = FakeRestoreApi("http://127.0.0.1:8090")
    result = wb.run_restore("auto-incr-x", wb.Settings(poll_seconds=0), api, "127.0.0.1:8090",
                            ["Chunks"], sleep=lambda _: None)
    assert result["status"] == "SUCCESS"
    assert api.calls == [("auto-incr-x", ["Chunks"])]
    assert api.polls == 2


def test_counting_inactive_tenants_requires_the_confirmed_endpoint(capsys):
    assert wb.main(["counts", "--activate-inactive"], {}) == 1
    assert "--confirm-endpoint None does not match '127.0.0.1:8080'" in capsys.readouterr().err


def test_weaviate_times_with_nanoseconds_and_the_zero_time_parse():
    assert wb.parse_time("2026-11-16T17:27:15.661017512Z") == \
        datetime(2026, 11, 16, 17, 27, 15, 661017, tzinfo=timezone.utc)
    assert wb.parse_time("0001-01-01T00:00:00Z") is None
    assert wb.parse_time("") is None


def test_invalid_settings_are_rejected():
    assert wb.main(["plan", "/nonexistent"], {"KEEP_CHAINS": "0"}) == 2
    assert wb.main(["plan", "/nonexistent"], {"FULL_INTERVAL_DAYS": "x"}) == 2
