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
# Environment: KEEP (backups to keep, default 30), MAX_AGE_HOURS (--check, default 26).
set -euo pipefail

usage() { echo "usage: $0 [--check] DB_PATH BACKUP_DIR" >&2; exit 2; }

MODE=backup
if [ "${1:-}" = "--check" ]; then MODE=check; shift; fi
[ $# -eq 2 ] || usage
DB="$1"
DIR="$2"
KEEP="${KEEP:-30}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-26}"
TAG=semant-sqlite-backup

log() { logger -t "$TAG" -- "$*" 2>/dev/null || true; echo "$(date -u +%FT%TZ) $*" >> "$DIR/backup.log" 2>/dev/null || true; }
fail() { log "FAILED: $*"; echo "$(date -u +%FT%TZ) FAILED: $*" > "$DIR/last_status" 2>/dev/null || true; echo "$TAG FAILED: $*" >&2; exit 1; }

integrity() { sqlite3 -readonly "$1" "PRAGMA integrity_check;" 2>&1; }

if [ "$MODE" = check ]; then
  newest=$(ls -1 "$DIR"/tasks_*.db 2>/dev/null | sort | tail -n 1) || true
  [ -n "$newest" ] || { echo "no backups in $DIR" >&2; exit 1; }
  age_h=$(( ($(date +%s) - $(stat -c %Y "$newest")) / 3600 ))
  echo "newest: $newest (${age_h} h old)"
  status=$(cat "$DIR/last_status" 2>/dev/null) || true
  echo "last run: ${status:-unknown}"
  case "$status" in *FAILED*) echo "the last backup run failed" >&2; exit 1 ;; esac
  [ "$(integrity "$newest")" = ok ] || { echo "integrity_check failed on $newest" >&2; exit 1; }
  [ "$age_h" -lt "$MAX_AGE_HOURS" ] || { echo "newest backup is older than ${MAX_AGE_HOURS} h" >&2; exit 1; }
  echo "ok"
  exit 0
fi

umask 077
mkdir -p "$DIR" || { echo "$TAG FAILED: cannot create $DIR" >&2; exit 1; }
[ -f "$DB" ] || fail "database $DB not found"
case "$DB$DIR" in *"'"*|*'?'*|*'#'*) fail "paths must not contain quotes, ? or #" ;; esac

ts=$(date -u +%Y-%m-%dT%H%M%SZ)
tmp="$DIR/.tasks_${ts}.db.partial"
final="$DIR/tasks_${ts}.db"
trap 'rm -f "$tmp"' EXIT

out=$(sqlite3 -bail "file:${DB}?mode=ro" ".timeout 60000" ".backup '${tmp}'" 2>&1) \
  || fail "sqlite3 .backup: $out"
check=$(integrity "$tmp")
[ "$check" = ok ] || fail "integrity_check of new backup: $check"
mv "$tmp" "$final"
ln -sfn "$(basename "$final")" "$DIR/latest.db"

# Bounded retention: keep the newest $KEEP backups.
ls -1 "$DIR"/tasks_*.db | sort | head -n "-$KEEP" | xargs -r rm -f --

size=$(stat -c %s "$final")
log "OK $final ($size bytes)"
echo "$(date -u +%FT%TZ) OK $final ($size bytes)" > "$DIR/last_status"
