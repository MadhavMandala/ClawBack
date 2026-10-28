#!/usr/bin/env bash
# Update the ClawBack backend on the VM to the latest commit of a branch, then restart it.
# Run on the VM:
#
#   sudo bash /opt/clawback/app/deploy/vm/update.sh            # the branch already checked out
#   sudo bash /opt/clawback/app/deploy/vm/update.sh main       # switch to another branch
#   sudo bash update.sh --archive /tmp/clawback.tar.gz         # code copied from a laptop instead of git
#
# It backs up the database first, keeps the last 7 backups, and rolls nothing back by itself: if the health
# check fails, the old backup and `git log` show where to go back to.

set -euo pipefail

APP_USER=clawback
APP_DIR=/opt/clawback/app
VENV=/opt/clawback/venv
DATA_DIR=/var/lib/clawback
ENV_FILE=/etc/clawback/clawback.env

say() { printf '\n== %s\n' "$*"; }
as_app() { sudo -u "$APP_USER" -H "$@"; }

[[ $EUID -eq 0 ]] || { echo "Run this as root: sudo bash update.sh"; exit 1; }

ARCHIVE=""
BRANCH=""
if [[ "${1:-}" == "--archive" ]]; then
  ARCHIVE="${2:?give the path to the .tar.gz}"
else
  BRANCH="${1:-}"
fi

# --- 1. Back up the database ----------------------------------------------------------------------------
db=$(grep -E '^CLAWBACK_DB_PATH=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true)
db="${db:-$DATA_DIR/clawback.db}"
if [[ -f "$db" ]]; then
  say "Backing up $db"
  stamp=$(date -u +%Y%m%d-%H%M%S)
  as_app sqlite3 "$db" ".backup '$DATA_DIR/backups/clawback-$stamp.db'"
  ls -1t "$DATA_DIR"/backups/clawback-*.db 2>/dev/null | tail -n +8 | xargs -r rm -f
fi

# --- 2. New code ----------------------------------------------------------------------------------------
if [[ -n "$ARCHIVE" ]]; then
  say "Unpacking $ARCHIVE into $APP_DIR"
  [[ ! -d "$APP_DIR/.git" ]] || { echo "$APP_DIR is a git checkout. Use update.sh without --archive."; exit 1; }
  tmp=$(mktemp -d)
  tar -xzf "$ARCHIVE" -C "$tmp"
  rm -rf "$APP_DIR.old"
  [[ -d "$APP_DIR" ]] && mv "$APP_DIR" "$APP_DIR.old"
  mv "$tmp" "$APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
  chmod 755 "$APP_DIR"
else
  BRANCH="${BRANCH:-$(as_app git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)}"
  say "Pulling $BRANCH"
  as_app git -C "$APP_DIR" fetch --prune origin
  # reset rather than merge: nobody edits code on the VM, and history may be rewritten before the repo goes public.
  as_app git -C "$APP_DIR" checkout -q -f -B "$BRANCH" "origin/$BRANCH"
  as_app git -C "$APP_DIR" reset -q --hard "origin/$BRANCH"
  as_app git -C "$APP_DIR" log -1 --format='Now at %h %s (%cr)'
fi

# --- 3. Dependencies and units --------------------------------------------------------------------------
say "Installing dependencies"
as_app "$VENV/bin/pip" install -q -e "$APP_DIR/backend"

for unit in clawback.service clawback-nightly.service clawback-nightly.timer; do
  install -m 644 "$APP_DIR/deploy/vm/$unit" "/etc/systemd/system/$unit"
done
# ClawBack's own 14-day journal (the units log there with LogNamespace=clawback).
if [[ -f "$APP_DIR/deploy/vm/journald@clawback.conf" ]]; then
  install -m 644 "$APP_DIR/deploy/vm/journald@clawback.conf" /etc/systemd/journald@clawback.conf
  systemctl try-restart systemd-journald@clawback.service
fi
systemctl daemon-reload

# --- 4. Restart and check -------------------------------------------------------------------------------
say "Restarting"
systemctl restart clawback.service
ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done

if "$VENV/bin/python" -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec("clawback.nightly") else 1)' 2>/dev/null; then
  systemctl enable --now clawback-nightly.timer >/dev/null
  echo "Nightly job: $(systemctl list-timers clawback-nightly.timer --no-legend | awk '{print "next run", $1, $2, $3}')"
else
  echo "Nightly job: clawback.nightly isn't in this code yet, so the timer stays off."
fi

if [[ $ok == 1 ]]; then
  echo "The API is up."
else
  echo "The API didn't answer within 30 seconds. Look at: journalctl --namespace=clawback -u clawback -n 80"
  exit 1
fi
