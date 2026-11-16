#!/usr/bin/env python3
"""Scheduled backups of the production Weaviate with chain-aware retention (#469).

    weaviate_backup.py backup BACKUP_ROOT STATE_DIR   take a full or an incremental backup,
                                                      then apply retention
    weaviate_backup.py check BACKUP_ROOT STATE_DIR    exit 1 unless the last run succeeded and
                                                      the newest backup is recent and SUCCESS
    weaviate_backup.py plan BACKUP_ROOT               print the chains, the next backup and
                                                      what retention would delete (read-only)
    weaviate_backup.py counts                         print object counts per collection and
                                                      tenant, and the aliases (read-only)
    weaviate_backup.py restore BACKUP_ID --confirm-endpoint HOST:PORT
                                                      restore into a disposable Weaviate

BACKUP_ROOT is the host directory that Weaviate's ``backup-filesystem`` module writes to
(bind-mounted at ``BACKUP_FILESYSTEM_PATH``); STATE_DIR holds ``last_status``, ``backup.log``,
``manifest.jsonl`` and the lock, outside BACKUP_ROOT so that Weaviate never lists them.

Each run creates a **full** backup when the newest successful full backup made by this
script is older than FULL_INTERVAL_DAYS less 12 hours (or there is none), otherwise an **incremental**
backup based on the newest successful backup of that full backup's chain. Weaviate records
each backup's base in ``BACKUP_ROOT/<id>/backup_config.json`` (``baseBackupId``); the chains
are read from there, so retention also sees backups made by hand.

Retention acts only on backups whose id starts with ``auto-`` (made by this script). It keeps
the newest KEEP_CHAINS chains of successful full backups and deletes an older chain, and any
failed or cancelled backup, by removing its directory, which is how a ``backup-filesystem``
backup is deleted (the API has no delete). A backup that any kept backup, including one made
by hand, depends on is never deleted. Older chains are deleted only once KEEP_CHAINS newer
full backups have succeeded, so the pool must hold KEEP_CHAINS + 1 chains for a while.

A backup is refused when the pool has less free space than MIN_FREE_GIB, or than
FREE_FACTOR times the disk usage of the newest successful full backup, whichever is larger.

Silent on success (cron mails only output); every run logs to syslog (tag
semant-weaviate-backup) and STATE_DIR/backup.log, writes RUNNING to STATE_DIR/last_status
first and replaces it with OK only after every step succeeded. See
deploy/README.md#weaviate-backup-469.

Environment: WEAVIATE_URL (default http://127.0.0.1:8080), FULL_INTERVAL_DAYS (7),
KEEP_CHAINS (2), MAX_AGE_HOURS (--check, 26), MIN_FREE_GIB (200), FREE_FACTOR (1.25),
TIMEOUT_HOURS (20), POLL_SECONDS (30), BACKUP_MOUNT (optional mountpoint that must be mounted
and contain BACKUP_ROOT and STATE_DIR).

Standard library only; runs on the host's Python 3.10.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

TAG = "semant-weaviate-backup"
PREFIX = "auto-"
ID_PATTERN = re.compile(r"^auto-(full|incr)-\d{8}-\d{6}$")
CONFIG_FILE = "backup_config.json"
TERMINAL_FAILED = {"FAILED", "CANCELED", "CANCELLED"}
PRODUCTION_ENDPOINTS = {"127.0.0.1:8080", "localhost:8080", "weaviate:8080"}
GIB = 1024 ** 3
FULL_SLACK = timedelta(hours=12)


class BackupError(RuntimeError):
    """A failure that is logged, recorded in last_status and makes the run exit 1."""


# ── Settings ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Settings:
    url: str = "http://127.0.0.1:8080"
    full_interval: timedelta = timedelta(days=7)
    keep_chains: int = 2
    max_age: timedelta = timedelta(hours=26)
    min_free_bytes: int = 200 * GIB
    free_factor: float = 1.25
    timeout: timedelta = timedelta(hours=20)
    poll_seconds: float = 30.0
    backup_mount: str = ""

    @classmethod
    def from_env(cls, env: dict[str, str] | os._Environ) -> "Settings":
        def number(name: str, default: float) -> float:
            raw = env.get(name, "")
            try:
                value = float(raw) if raw else default
            except ValueError:
                raise BackupError(f"{name}={raw!r} is not a number") from None
            if value < 0:
                raise BackupError(f"{name} must not be negative")
            return value

        keep = int(number("KEEP_CHAINS", 2))
        if keep < 1:
            raise BackupError("KEEP_CHAINS must be at least 1")
        return cls(
            url=env.get("WEAVIATE_URL", "") or cls.url,
            full_interval=timedelta(days=number("FULL_INTERVAL_DAYS", 7)),
            keep_chains=keep,
            max_age=timedelta(hours=number("MAX_AGE_HOURS", 26)),
            min_free_bytes=int(number("MIN_FREE_GIB", 200) * GIB),
            free_factor=number("FREE_FACTOR", 1.25),
            timeout=timedelta(hours=number("TIMEOUT_HOURS", 20)),
            poll_seconds=number("POLL_SECONDS", 30),
            backup_mount=env.get("BACKUP_MOUNT", ""),
        )


# ── Time ──────────────────────────────────────────────────────────────────

_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")


def parse_time(value: str | None) -> datetime | None:
    """Weaviate's RFC 3339 times (nanoseconds, ``Z``) as aware UTC; None for empty or year 1.

    ``datetime.fromisoformat`` of Python 3.10 accepts neither nanoseconds nor ``Z``.
    """
    if not value:
        return None
    match = _TIME.match(value.strip())
    if not match:
        raise ValueError(f"unrecognised time {value!r}")
    base, fraction, zone = match.groups()
    micro = (fraction or ".0")[1:7].ljust(6, "0")
    offset = "+00:00" if zone in (None, "Z") else zone
    parsed = datetime.fromisoformat(f"{base}.{micro}{offset}").astimezone(timezone.utc)
    return None if parsed.year <= 1 else parsed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(kind: str, moment: datetime) -> str:
    return f"{PREFIX}{kind}-{moment.astimezone(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


# ── Backups on disk ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Backup:
    id: str
    status: str
    base: str
    started: datetime | None
    completed: datetime | None
    pre_compression_bytes: int | None = None

    @property
    def auto(self) -> bool:
        return bool(ID_PATTERN.match(self.id))

    @property
    def full(self) -> bool:
        return not self.base

    @property
    def ok(self) -> bool:
        return self.status == "SUCCESS"


def read_backup(directory: Path) -> Backup:
    """The backup in ``directory``; status UNKNOWN when its config is missing or unreadable
    (a backup still being written, or a broken one): such a backup is never deleted."""
    try:
        config = json.loads((directory / CONFIG_FILE).read_text())
        return Backup(
            id=str(config.get("id") or directory.name),
            status=str(config.get("status") or "UNKNOWN").upper(),
            base=str(config.get("baseBackupId") or ""),
            started=parse_time(config.get("startedAt")),
            completed=parse_time(config.get("completedAt")),
            pre_compression_bytes=config.get("preCompressionSizeBytes"),
        )
    except (OSError, ValueError, AttributeError):
        return Backup(directory.name, "UNKNOWN", "", None, None)


def scan(root: Path) -> dict[str, Backup]:
    """Every backup directory under ``root``, by id (the directory name)."""
    if not root.is_dir():
        raise BackupError(f"backup root {root} does not exist")
    backups = {}
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and not entry.is_symlink():
            backup = read_backup(entry)
            backups[entry.name] = Backup(entry.name, backup.status, backup.base, backup.started,
                                         backup.completed, backup.pre_compression_bytes)
    return backups


def chain_root(backups: dict[str, Backup], backup_id: str) -> str | None:
    """The full backup that ``backup_id`` ultimately depends on; None when a base is missing."""
    seen = set()
    current = backups.get(backup_id)
    while current is not None and current.base:
        if current.id in seen:
            return None
        seen.add(current.id)
        current = backups.get(current.base)
    return current.id if current is not None else None


def _started(backup: Backup) -> datetime:
    return backup.started or datetime.min.replace(tzinfo=timezone.utc)


def auto_fulls(backups: dict[str, Backup]) -> list[Backup]:
    """Successful full backups made by this script, newest first."""
    return sorted((b for b in backups.values() if b.auto and b.full and b.ok), key=_started, reverse=True)


def disk_usage(path: Path) -> int:
    """Bytes allocated on disk (after ZFS compression), like ``du``."""
    total = 0
    for directory, _, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(directory, name)).st_blocks * 512
            except OSError:
                pass
    return total


def human(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def free_bytes(path: Path) -> int:
    stats = os.statvfs(path)
    return stats.f_bavail * stats.f_frsize


# ── Planning ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NextBackup:
    id: str
    kind: str  # full | incr
    base: str  # "" for a full backup
    reason: str


def next_backup(backups: dict[str, Backup], settings: Settings, now: datetime) -> NextBackup:
    fulls = auto_fulls(backups)
    if not fulls:
        return NextBackup(new_id("full", now), "full", "", "no successful full backup made by this script")
    newest = fulls[0]
    # The slack lets a daily run at a fixed time start the weekly full backup on the 7th day,
    # although the previous one started a few seconds after its own run started.
    if newest.started is None or now - newest.started >= settings.full_interval - FULL_SLACK:
        return NextBackup(new_id("full", now), "full", "",
                          f"{newest.id} is older than {settings.full_interval.days} days")
    chain = [b for b in backups.values() if b.ok and chain_root(backups, b.id) == newest.id]
    base = max(chain, key=_started)
    return NextBackup(new_id("incr", now), "incr", base.id, f"chain of {newest.id}")


def retention(backups: dict[str, Backup], keep_chains: int) -> tuple[list[str], list[str]]:
    """(ids to delete, ids kept only because another backup depends on them).

    Candidates are this script's backups that are failed or cancelled, or whose chain is
    older than the newest ``keep_chains`` successful full backups. A candidate is kept when
    any backup that stays (made by this script or by hand, finished or not) depends on it.
    """
    old_fulls = {b.id for b in auto_fulls(backups)[keep_chains:]}
    delete = set()
    for backup in backups.values():
        if not backup.auto:
            continue
        if backup.status in TERMINAL_FAILED:
            delete.add(backup.id)
        elif backup.ok and chain_root(backups, backup.id) in old_fulls:
            delete.add(backup.id)
    protected: set[str] = set()
    changed = True
    while changed:  # a protected backup protects its own bases too
        changed = False
        for backup in backups.values():
            if backup.id in delete:
                continue
            base, steps = backup.base, 0
            while base and steps <= len(backups):
                if base in delete:
                    delete.discard(base)
                    protected.add(base)
                    changed = True
                parent = backups.get(base)
                base, steps = (parent.base if parent else ""), steps + 1
    return sorted(delete), sorted(protected)


# ── Weaviate REST ─────────────────────────────────────────────────────────

class Weaviate:
    def __init__(self, url: str, timeout: float = 60.0):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None) -> object:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(f"{self.url}{path}", data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise BackupError(f"{method} {path}: HTTP {e.code} {detail}") from None
        except (urllib.error.URLError, OSError) as e:
            raise BackupError(f"{method} {path}: {e}") from None
        return json.loads(raw) if raw else None

    def create(self, backup_id: str, base: str = "", include: list[str] | None = None) -> dict:
        body: dict = {"id": backup_id}
        if base:
            body["incremental_base_backup_id"] = base
        if include:
            body["include"] = include
        return self._request("POST", "/v1/backups/filesystem", body)  # type: ignore[return-value]

    def status(self, backup_id: str) -> dict:
        return self._request("GET", f"/v1/backups/filesystem/{urllib.parse.quote(backup_id)}")  # type: ignore[return-value]

    def restore(self, backup_id: str, include: list[str] | None = None) -> dict:
        body: dict = {"include": include} if include else {}
        return self._request("POST", f"/v1/backups/filesystem/{urllib.parse.quote(backup_id)}/restore",
                             body)  # type: ignore[return-value]

    def restore_status(self, backup_id: str) -> dict:
        return self._request(  # type: ignore[return-value]
            "GET", f"/v1/backups/filesystem/{urllib.parse.quote(backup_id)}/restore")

    def counts(self) -> dict[str, object]:
        """Object counts per collection and per tenant (inactive tenants by status), and the aliases."""
        schema = self._request("GET", "/v1/schema") or {}
        result: dict[str, object] = {}
        for cls in sorted(schema.get("classes", []), key=lambda c: c["class"]):  # type: ignore[union-attr]
            name = cls["class"]
            if (cls.get("multiTenancyConfig") or {}).get("enabled"):
                tenants = self._request("GET", f"/v1/schema/{name}/tenants") or []
                for tenant in sorted(tenants, key=lambda t: t["name"]):  # type: ignore[union-attr]
                    state = tenant.get("activityStatus", "")
                    key = f"{name}/{tenant['name']}"
                    result[key] = self._count(name, tenant["name"]) if state in ("HOT", "ACTIVE") else state
            else:
                result[name] = self._count(name)
        try:
            aliases = (self._request("GET", "/v1/aliases") or {}).get("aliases", [])  # type: ignore[union-attr]
        except BackupError:
            aliases = []
        for alias in sorted(aliases, key=lambda a: a["alias"]):
            result[f"alias:{alias['alias']}"] = alias["class"]
        return result

    def _count(self, name: str, tenant: str | None = None) -> int:
        argument = f'(tenant: {json.dumps(tenant)})' if tenant else ""
        response = self._request("POST", "/v1/graphql",
                                 {"query": f"{{ Aggregate {{ {name}{argument} {{ meta {{ count }} }} }} }}"})
        if not isinstance(response, dict) or response.get("errors"):
            raise BackupError(f"counting {name} {tenant or ''}: {response}")
        return int(response["data"]["Aggregate"][name][0]["meta"]["count"])


def wait_for(get_status: Callable[[], dict], settings: Settings, what: str,
             sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> dict:
    deadline = clock() + settings.timeout.total_seconds()
    while True:
        status = get_status()
        state = str(status.get("status", "")).upper()
        if state == "SUCCESS" or state in TERMINAL_FAILED:
            return status
        if clock() >= deadline:
            raise BackupError(f"{what} still {state or 'unknown'} after {settings.timeout}; left running")
        sleep(settings.poll_seconds)


# ── Logging, status, lock ─────────────────────────────────────────────────

class Journal:
    def __init__(self, state_dir: Path, clock: Callable[[], datetime]):
        self.state_dir = state_dir
        self.clock = clock

    def log(self, message: str) -> None:
        try:
            import syslog
            syslog.openlog(TAG)
            syslog.syslog(message)
        except Exception:
            pass
        try:
            with open(self.state_dir / "backup.log", "a") as handle:
                handle.write(f"{stamp(self.clock())} {message}\n")
        except OSError:
            pass

    def status(self, text: str) -> None:
        path = self.state_dir / "last_status"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(f"{stamp(self.clock())} {text}\n")
        tmp.replace(path)

    def last_status(self) -> str:
        try:
            return (self.state_dir / "last_status").read_text().strip()
        except OSError:
            return ""

    def manifest(self, record: dict) -> None:
        with open(self.state_dir / "manifest.jsonl", "a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def check_mount(settings: Settings, paths: Iterable[Path]) -> None:
    if not settings.backup_mount:
        return
    mount = Path(settings.backup_mount)
    for path in paths:
        resolved = path.resolve()
        if resolved != mount.resolve() and mount.resolve() not in resolved.parents:
            raise BackupError(f"{path} is not on BACKUP_MOUNT {mount}")
    if not os.path.ismount(mount):
        raise BackupError(f"BACKUP_MOUNT {mount} is not mounted")


def delete_backup(root: Path, backup_id: str) -> None:
    if not ID_PATTERN.match(backup_id):
        raise BackupError(f"refusing to delete {backup_id!r}: not made by this script")
    target = root / backup_id
    if target.is_symlink() or target.resolve().parent != root.resolve():
        raise BackupError(f"refusing to delete {target}: not a directory directly in {root}")
    shutil.rmtree(target)


# ── Commands ──────────────────────────────────────────────────────────────

def run_backup(root: Path, state_dir: Path, settings: Settings, api: Weaviate,
               clock: Callable[[], datetime] = utc_now, sleep: Callable[[float], None] = time.sleep) -> str:
    """One scheduled run; returns the id of the new backup."""
    journal = Journal(state_dir, clock)
    journal.status("RUNNING")
    backups = scan(root)
    plan = next_backup(backups, settings, clock())
    fulls = [b for b in backups.values() if b.full and b.ok]
    newest_full = max(fulls, key=_started) if fulls else None
    full_size = disk_usage(root / newest_full.id) if newest_full else 0
    required = max(settings.min_free_bytes, int(settings.free_factor * full_size))
    available = free_bytes(root)
    if available < required:
        raise BackupError(f"only {available / GIB:.0f} GiB free in {root}, {required / GIB:.0f} GiB required "
                          f"(MIN_FREE_GIB, or FREE_FACTOR x {full_size / GIB:.0f} GiB of {newest_full.id if newest_full else '-'})")
    journal.log(f"START {plan.id} kind={plan.kind} base={plan.base or '-'} ({plan.reason}); "
                f"{available / GIB:.0f} GiB free")
    started = clock()
    api.create(plan.id, plan.base)
    final = wait_for(lambda: api.status(plan.id), settings, f"backup {plan.id}", sleep=sleep)
    state = str(final.get("status", "")).upper()
    on_disk = read_backup(root / plan.id)
    record = {"id": plan.id, "kind": plan.kind, "base": plan.base, "status": state,
              "started": stamp(started), "finished": stamp(clock()),
              "pre_compression_bytes": on_disk.pre_compression_bytes}
    if state != "SUCCESS":
        journal.manifest(record)
        raise BackupError(f"backup {plan.id} ended {state}: {final.get('error', '')}")
    if not (root / plan.id).is_dir() or on_disk.status != "SUCCESS":
        journal.manifest({**record, "status": "NOT_ON_DISK"})
        raise BackupError(f"backup {plan.id} succeeded but {root / plan.id} holds no successful backup: "
                          "is BACKUP_ROOT the directory mounted at BACKUP_FILESYSTEM_PATH?")
    if on_disk.base != plan.base:
        journal.manifest({**record, "status": "BASE_MISMATCH"})
        raise BackupError(f"backup {plan.id} records base {on_disk.base!r}, expected {plan.base!r}")
    record["disk_bytes"] = disk_usage(root / plan.id)
    record["chain"] = chain_root(scan(root), plan.id)

    delete, protected = retention(scan(root), settings.keep_chains)
    for backup_id in delete:
        delete_backup(root, backup_id)
        journal.log(f"DELETED {backup_id} (retention)")
    if protected:
        journal.log(f"KEPT {' '.join(protected)}: another backup depends on them")
    record["deleted"] = delete
    journal.manifest(record)
    summary = (f"OK id={plan.id} kind={plan.kind} base={plan.base or '-'} "
               f"disk={human(record['disk_bytes']).replace(' ', '')} deleted={len(delete)}")
    journal.status(summary)
    journal.log(summary)
    return plan.id


def run_check(root: Path, state_dir: Path, settings: Settings, api: Weaviate,
              clock: Callable[[], datetime] = utc_now) -> list[str]:
    """Problems with the backups; empty when all is well. Prints a short summary."""
    problems = []
    try:
        check_mount(settings, [root, state_dir])
        backups = scan(root)
    except BackupError as e:
        return [str(e)]
    mine = sorted((b for b in backups.values() if b.auto), key=_started, reverse=True)
    status = Journal(state_dir, clock).last_status()
    print(f"last run: {status or 'unknown'}")
    if not mine:
        return problems + [f"no backups made by this script in {root}"]
    newest = mine[0]
    age = clock() - (newest.completed or newest.started or datetime.min.replace(tzinfo=timezone.utc))
    print(f"newest: {newest.id} {newest.status} base={newest.base or '-'} "
          f"({age.total_seconds() / 3600:.1f} h old); chains: {len(auto_fulls(backups))}")
    if f" OK id={newest.id} " not in f" {status} ":
        problems.append(f"the last run did not finish successfully for {newest.id}")
    if not newest.ok:
        problems.append(f"{newest.id} is {newest.status} on disk")
    elif chain_root(backups, newest.id) is None:
        problems.append(f"{newest.id} depends on a missing backup")
    if age > settings.max_age:
        problems.append(f"the newest backup is older than {settings.max_age.total_seconds() / 3600:.0f} h")
    try:
        state = str(api.status(newest.id).get("status", "")).upper()
        if state != "SUCCESS":
            problems.append(f"Weaviate reports {newest.id} as {state or 'unknown'}")
    except BackupError as e:
        problems.append(f"cannot read the status from Weaviate: {e}")
    return problems


def run_plan(root: Path, settings: Settings, clock: Callable[[], datetime] = utc_now) -> None:
    backups = scan(root)
    for backup in sorted(backups.values(), key=_started):
        print(f"{backup.id}\t{backup.status}\tbase={backup.base or '-'}\tchain={chain_root(backups, backup.id) or 'BROKEN'}"
              f"\t{'auto' if backup.auto else 'manual'}\tstarted={stamp(backup.started) if backup.started else '-'}")
    plan = next_backup(backups, settings, clock())
    print(f"next: {plan.id} kind={plan.kind} base={plan.base or '-'} ({plan.reason})")
    delete, protected = retention(backups, settings.keep_chains)
    print(f"retention would delete: {' '.join(delete) or 'nothing'}")
    if protected:
        print(f"kept because another backup depends on them: {' '.join(protected)}")


def run_restore(backup_id: str, settings: Settings, api: Weaviate, confirm: str,
                include: list[str] | None, sleep: Callable[[float], None] = time.sleep) -> dict:
    endpoint = urllib.parse.urlsplit(api.url).netloc
    if confirm != endpoint:
        raise BackupError(f"--confirm-endpoint {confirm!r} does not match {endpoint!r}")
    if endpoint in PRODUCTION_ENDPOINTS:
        raise BackupError(f"refusing to restore into {endpoint}: restore only into a disposable Weaviate")
    api.restore(backup_id, include)
    return wait_for(lambda: api.restore_status(backup_id), settings, f"restore of {backup_id}", sleep=sleep)


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None,
         clock: Callable[[], datetime] = utc_now, sleep: Callable[[float], None] = time.sleep,
         api: Weaviate | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "check"):
        command = sub.add_parser(name)
        command.add_argument("backup_root", type=Path)
        command.add_argument("state_dir", type=Path)
    sub.add_parser("plan").add_argument("backup_root", type=Path)
    sub.add_parser("counts")
    restore = sub.add_parser("restore")
    restore.add_argument("backup_id")
    restore.add_argument("--confirm-endpoint", required=True, help="HOST:PORT of WEAVIATE_URL")
    restore.add_argument("--include", nargs="*", help="collections to restore (default: all)")
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env(os.environ if environ is None else environ)
    except BackupError as e:
        print(f"{TAG}: {e}", file=sys.stderr)
        return 2
    api = api or Weaviate(settings.url)

    try:
        if args.command == "plan":
            run_plan(args.backup_root, settings, clock)
            return 0
        if args.command == "counts":
            for key, value in api.counts().items():
                print(f"{key}\t{value}")
            return 0
        if args.command == "restore":
            result = run_restore(args.backup_id, settings, api, args.confirm_endpoint, args.include, sleep)
            print(json.dumps(result, sort_keys=True))
            return 0 if str(result.get("status", "")).upper() == "SUCCESS" else 1
        if args.command == "check":
            problems = run_check(args.backup_root, args.state_dir, settings, api, clock)
            for problem in problems:
                print(problem, file=sys.stderr)
            if not problems:
                print("ok")
            return 1 if problems else 0
    except BackupError as e:
        print(f"{TAG}: {e}", file=sys.stderr)
        return 1

    # backup
    root, state_dir = args.backup_root, args.state_dir
    try:
        check_mount(settings, [root, state_dir])
        state_dir.mkdir(parents=True, exist_ok=True)
    except (BackupError, OSError) as e:
        Journal(state_dir, clock).log(f"FAILED: {e}")
        print(f"{TAG} FAILED: {e}", file=sys.stderr)
        return 1
    lock = open(state_dir / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        Journal(state_dir, clock).log("FAILED: another run holds the lock")
        print(f"{TAG} FAILED: another run holds {state_dir / 'lock'}", file=sys.stderr)
        return 1
    journal = Journal(state_dir, clock)
    try:
        run_backup(root, state_dir, settings, api, clock, sleep)
        return 0
    except Exception as e:  # record every failure, expected or not, as FAILED
        message = str(e) if isinstance(e, BackupError) else f"unexpected {type(e).__name__}: {e}"
        journal.log(f"FAILED: {message}")
        try:
            journal.status(f"FAILED: {message}")
        except OSError:
            pass
        print(f"{TAG} FAILED: {message}", file=sys.stderr)
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
