#!/usr/bin/bash
# Tests for sqlite_backup.sh on a synthetic database in a temporary directory (#399).
# Needs bash, sqlite3 and util-linux (mountpoint). Usage: bash deploy/test_sqlite_backup.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/sqlite_backup.sh"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
DB="$T/tasks.db"
B="$T/backups"
failures=0

ok() { echo "ok   - $1"; }
not_ok() { echo "FAIL - $1"; failures=$((failures + 1)); }
expect_success() { local name=$1; shift; if "$@" >"$T/out" 2>&1; then ok "$name"; else not_ok "$name"; cat "$T/out"; fi; }
expect_failure() { local name=$1; shift; if "$@" >"$T/out" 2>&1; then not_ok "$name"; cat "$T/out"; else ok "$name"; fi; }
run() { bash "$SCRIPT" "$@"; }
status_is_in() { case "$(cat "$1/last_status" 2>/dev/null)" in *"$2"*) ok "last_status contains '$2'" ;; *) not_ok "last_status contains '$2' (got: $(cat "$1/last_status" 2>/dev/null))" ;; esac; }
status_is() { status_is_in "$B" "$1"; }

sqlite3 "$DB" "CREATE TABLE user(id INTEGER PRIMARY KEY, email TEXT); INSERT INTO user(email) VALUES ('a@example.org'), ('b@example.org');"

# Successful backup and check.
expect_success "backup succeeds" run "$DB" "$B"
status_is " OK "
[ "$(sqlite3 "$B/latest.db" 'SELECT count(*) FROM user;')" = 2 ] && ok "backup has the rows" || not_ok "backup has the rows"
[ "$(stat -c %a "$B")" = 700 ] && ok "backup directory is 700" || not_ok "backup directory is 700"
expect_success "check accepts a fresh successful backup" run --check "$DB" "$B"
expect_success "check accepts a trailing slash on BACKUP_DIR" run --check "$DB" "$B/"

# Bounded retention.
for d in 2020-01-01 2020-01-02 2020-01-03; do cp "$B/latest.db" "$B/tasks_${d}T000000Z.db"; done
KEEP=2 run "$DB" "$B" >/dev/null 2>&1
[ "$(ls "$B"/tasks_*.db | wc -l)" = 2 ] && ok "KEEP=2 keeps two backups" || not_ok "KEEP=2 keeps two backups"
[ ! -e "$B/tasks_2020-01-01T000000Z.db" ] && ok "oldest backups are pruned" || not_ok "oldest backups are pruned"

# Missing or unfinished status.
mv "$B/last_status" "$T/last_status.ok"
expect_failure "check rejects a missing last_status" run --check "$DB" "$B"
echo "2026-01-01T00:00:00Z RUNNING" > "$B/last_status"
expect_failure "check rejects an unfinished (RUNNING) run" run --check "$DB" "$B"
newest=$(ls "$B"/tasks_*.db | sort | tail -n 1)
echo "2026-01-01T00:00:00Z OK $B/tasks_2020-01-01T000000Z.db (1 bytes)" > "$B/last_status"
expect_failure "check rejects an OK status for another backup" run --check "$DB" "$B"
mv "$T/last_status.ok" "$B/last_status"

# An unexpected command failure (not via fail()) after an earlier OK run is recorded as FAILED.
mkdir "$T/bin"
printf '#!/bin/sh\necho "ln: simulated failure" >&2\nexit 1\n' > "$T/bin/ln"
chmod +x "$T/bin/ln"
expect_failure "backup fails when ln fails" env PATH="$T/bin:$PATH" bash "$SCRIPT" "$DB" "$B"
status_is "FAILED: unexpected error"
grep -q "FAILED: unexpected error" "$B/backup.log" && ok "unexpected failure is logged" || not_ok "unexpected failure is logged"
expect_failure "check rejects a recent backup after an unexpected failure" run --check "$DB" "$B"
ls "$B"/.tasks_*.partial >/dev/null 2>&1 && not_ok "no partial file is left" || ok "no partial file is left"

# Expected failure: missing database.
expect_success "backup recovers" run "$DB" "$B"
expect_failure "backup fails for a missing database" run "$T/missing.db" "$B"
status_is "FAILED: database"
expect_failure "check rejects the run after the failure" run --check "$DB" "$B"

# Stale and corrupt backups.
expect_success "backup recovers again" run "$DB" "$B"
newest=$(ls "$B"/tasks_*.db | sort | tail -n 1)
touch -d '2 days ago' "$newest"
expect_failure "check rejects a stale backup" run --check "$DB" "$B"
touch "$newest"
printf 'garbage' | dd of="$newest" bs=1 seek=100 conv=notrunc status=none
expect_failure "check rejects a corrupt backup" run --check "$DB" "$B"

# A hot journal (writer killed mid-transaction, #406): the read-only backup must refuse to copy
# the uncommitted pages and leave the journal for SQLite to roll back.
H="$T/hot"
mkdir "$H"
sqlite3 "$H/tasks.db" "CREATE TABLE item(id INTEGER PRIMARY KEY, value TEXT); WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 2000) INSERT INTO item(value) SELECT 'committed' || printf('%.500c', 'x') FROM n;"
(sqlite3 "$H/tasks.db" "PRAGMA cache_size=10; BEGIN; UPDATE item SET value = 'uncommitted';" '.system kill -9 $PPID'; true) 2>/dev/null
[ -s "$H/tasks.db-journal" ] && ok "hot journal created" || not_ok "hot journal created"
expect_failure "backup fails while a hot journal exists" run "$H/tasks.db" "$H/backups"
status_is_in "$H/backups" "FAILED: sqlite3 .backup"
[ -s "$H/tasks.db-journal" ] && ok "hot journal is kept" || not_ok "hot journal is kept"
sqlite3 "$H/tasks.db" "PRAGMA integrity_check;" >/dev/null   # a read-write open rolls the journal back
expect_success "backup succeeds after the rollback" run "$H/tasks.db" "$H/backups"
[ "$(sqlite3 "$H/backups/latest.db" "SELECT count(*) FROM item WHERE value LIKE 'committed%';")" = 2000 ] \
  && ok "backup has only committed rows" || not_ok "backup has only committed rows"

# BACKUP_MOUNT: an unmounted pool must not lead to backups on the parent filesystem.
mkdir "$T/pool"
expect_failure "backup fails when BACKUP_MOUNT is not mounted" env BACKUP_MOUNT="$T/pool" bash "$SCRIPT" "$DB" "$T/pool/app/backups"
[ ! -e "$T/pool/app" ] && ok "unmounted pool: directory not created" || not_ok "unmounted pool: directory not created"
expect_failure "check fails when BACKUP_MOUNT is not mounted" env BACKUP_MOUNT="$T/pool" bash "$SCRIPT" --check "$DB" "$T/pool/app/backups"
expect_failure "backup fails when BACKUP_DIR is outside BACKUP_MOUNT" env BACKUP_MOUNT=/proc bash "$SCRIPT" "$DB" "$T/other"
[ ! -e "$T/other" ] && ok "outside mount: directory not created" || not_ok "outside mount: directory not created"
expect_success "backup succeeds under a mounted BACKUP_MOUNT" env BACKUP_MOUNT=/ bash "$SCRIPT" "$DB" "$T/mounted"
expect_success "check succeeds under a mounted BACKUP_MOUNT" env BACKUP_MOUNT=/ bash "$SCRIPT" --check "$DB" "$T/mounted"

# Usage.
expect_failure "usage error without arguments" run

if [ "$failures" -eq 0 ]; then echo "all tests passed"; else echo "$failures test(s) failed"; exit 1; fi
