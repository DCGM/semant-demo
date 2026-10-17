#!/usr/bin/bash
# Consistent backup of the app SQLite database (tasks.db: users, RAG feedback, LLM quota), #399.
#
#   sqlite_backup.sh DB_PATH BACKUP_DIR           take a backup, verify it, prune old ones
#   sqlite_backup.sh --check DB_PATH BACKUP_DIR   exit 1 unless the last run succeeded and the
#                                                 newest backup is recent and intact
#
# The copy uses the SQLite online backup API (sqlite3 .backup) on a read-only connection, so it
# waits for the app's locks instead of copying a file in the middle of a write. Each backup is
# checked with PRAGMA integrity_check before it replaces anything. The script is silent on
# success (cron mails only output) and logs every run to syslog (tag semant-sqlite-backup) and
# BACKUP_DIR/backup.log. See deploy/README.md#sqlite-backup-399.
#
# Every run first records RUNNING in BACKUP_DIR/last_status and replaces it with OK only after
# all steps succeed; any failure, expected or not, records FAILED. --check accepts only an OK
# status that names the newest backup.
#
# Environment: KEEP (backups to keep, default 30), MAX_AGE_HOURS (--check, default 26),
# BACKUP_MOUNT (optional mountpoint that must be mounted and contain BACKUP_DIR, so an
# unmounted pool does not silently send backups to the root filesystem).
set -euo pipefail

usage() { echo "usage: $0 [--check] DB_PATH BACKUP_DIR" >&2; exit 2; }

MODE=backup
if [ "${1:-}" = "--check" ]; then MODE=check; shift; fi
[ $# -eq 2 ] || usage
DB="$1"
DIR="${2%/}"
KEEP="${KEEP:-30}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-26}"
BACKUP_MOUNT="${BACKUP_MOUNT:-}"
TAG=semant-sqlite-backup

log() { logger -t "$TAG" -- "$*" 2>/dev/null || true; echo "$(date -u +%FT%TZ) $*" >> "$DIR/backup.log" 2>/dev/null || true; }
status() { echo "$(date -u +%FT%TZ) $*" > "$DIR/last_status"; }
failed=
fail() { failed=1; log "FAILED: $*"; status "FAILED: $*" 2>/dev/null || true; echo "$TAG FAILED: $*" >&2; exit 1; }

integrity() { sqlite3 -readonly "$1" "PRAGMA integrity_check;" 2>&1; }

check_mount() {
  [ -n "$BACKUP_MOUNT" ] || return 0
  case "${DIR%/}/" in "${BACKUP_MOUNT%/}/"*) ;; *) return 1 ;; esac
  mountpoint -q "$BACKUP_MOUNT"
}

if [ "$MODE" = check ]; then
  check_mount || { echo "$BACKUP_MOUNT is not mounted or does not contain $DIR" >&2; exit 1; }
  newest=$(ls -1 "$DIR"/tasks_*.db 2>/dev/null | sort | tail -n 1) || true
  [ -n "$newest" ] || { echo "no backups in $DIR" >&2; exit 1; }
  age_h=$(( ($(date +%s) - $(stat -c %Y "$newest")) / 3600 ))
  echo "newest: $newest (${age_h} h old)"
  status=$(cat "$DIR/last_status" 2>/dev/null) || true
  echo "last run: ${status:-unknown}"
  case "$status" in
    *" OK "*"/${newest##*/} "*) ;;
    *FAILED*) echo "the last backup run failed" >&2; exit 1 ;;
    *) echo "the last backup run did not finish successfully for $newest" >&2; exit 1 ;;
  esac
  [ "$(integrity "$newest")" = ok ] || { echo "integrity_check failed on $newest" >&2; exit 1; }
  [ "$age_h" -lt "$MAX_AGE_HOURS" ] || { echo "newest backup is older than ${MAX_AGE_HOURS} h" >&2; exit 1; }
  echo "ok"
  exit 0
fi

umask 077
# Record unexpected failures (set -e exits outside fail()) as FAILED too.
tmp=
err_at=
trap 'err_at="line $LINENO: $BASH_COMMAND"' ERR
trap 'rc=$?; [ -z "$tmp" ] || rm -f "$tmp"
  if [ "$rc" -ne 0 ] && [ -z "$failed" ]; then fail "unexpected error (exit $rc) at ${err_at:-unknown}"; fi' EXIT

check_mount || { failed=1; log "FAILED: $BACKUP_MOUNT is not mounted or does not contain $DIR"
  echo "$TAG FAILED: $BACKUP_MOUNT is not mounted or does not contain $DIR" >&2; exit 1; }
mkdir -p "$DIR" || { failed=1; log "FAILED: cannot create $DIR"; echo "$TAG FAILED: cannot create $DIR" >&2; exit 1; }
status RUNNING
[ -f "$DB" ] || fail "database $DB not found"
case "$DB$DIR" in *"'"*|*'?'*|*'#'*) fail "paths must not contain quotes, ? or #" ;; esac

ts=$(date -u +%Y-%m-%dT%H%M%SZ)
tmp="$DIR/.tasks_${ts}.db.partial"
final="$DIR/tasks_${ts}.db"

out=$(sqlite3 -bail "file:${DB}?mode=ro" ".timeout 60000" ".backup '${tmp}'" 2>&1) \
  || fail "sqlite3 .backup: $out"
check=$(integrity "$tmp")
[ "$check" = ok ] || fail "integrity_check of new backup: $check"
mv "$tmp" "$final"
ln -sfn "$(basename "$final")" "$DIR/latest.db"

# Bounded retention: keep the newest $KEEP backups.
ls -1 "$DIR"/tasks_*.db | sort | head -n "-$KEEP" | xargs -r rm -f --

size=$(stat -c %s "$final")
status "OK $final ($size bytes)"
log "OK $final ($size bytes)"
