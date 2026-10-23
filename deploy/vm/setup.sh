#!/usr/bin/env bash
# ClawBack backend on one small Ubuntu 24.04 VM. See docs/DEPLOY.md for the whole runbook.
#
# Run as root on the VM. Safe to run again: each step checks what is already there.
#
#   sudo bash setup.sh
#
# First run: installs packages, creates the clawback user, makes a read-only GitHub deploy key, prints its
# public half and stops. Add that key to the repo on GitHub (Settings > Deploy keys, no write access), then run
# the script again. The second run clones the code, installs it, and starts the API behind Caddy with HTTPS.
#
# Settings, all optional, passed as environment variables:
#   CLAWBACK_HOST  public host name. Default: <public-ip-with-dashes>.sslip.io
#   PUBLIC_IP      the VM's public IPv4 address. Default: looked up once from api.ipify.org
#   REPO           git URL. Default: git@github.com:MadhavMandala/ClawBack.git
#   BRANCH         branch to run. Default: main
#   DATA_DEVICE    a separate data disk for the database, such as /dev/vdb. Formatted ONLY if it has no
#                  filesystem yet, then mounted at /var/lib/clawback. Leave unset to keep the data on the boot disk.
#   SKIP_CLONE=1   the code was copied to /opt/clawback/app by hand (scp), so don't use git.
#
# Example:  sudo DATA_DEVICE=/dev/vdb BRANCH=main bash setup.sh

set -euo pipefail

REPO="${REPO:-git@github.com:MadhavMandala/ClawBack.git}"
BRANCH="${BRANCH:-main}"
SKIP_CLONE="${SKIP_CLONE:-0}"
DATA_DEVICE="${DATA_DEVICE:-}"

APP_USER=clawback
HOME_DIR=/opt/clawback
APP_DIR=$HOME_DIR/app
VENV=$HOME_DIR/venv
DATA_DIR=/var/lib/clawback
ENV_DIR=/etc/clawback
ENV_FILE=$ENV_DIR/clawback.env
KEY=$HOME_DIR/.ssh/clawback_deploy
# GitHub's published Ed25519 host key (docs.github.com, "GitHub's SSH key fingerprints").
GITHUB_HOST_KEY="github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"

say() { printf '\n== %s\n' "$*"; }
as_app() { sudo -u "$APP_USER" -H "$@"; }

[[ $EUID -eq 0 ]] || { echo "Run this as root: sudo bash setup.sh"; exit 1; }
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || echo "Warning: written for Ubuntu 24.04; this is ${PRETTY_NAME:-unknown}."

# --- 1. Packages ----------------------------------------------------------------------------------------
say "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git sqlite3 curl ufw \
  debian-keyring debian-archive-keyring apt-transport-https gnupg

python3 - <<'PY' || { echo "ClawBack needs Python 3.12 or newer. Use an Ubuntu 24.04 image."; exit 1; }
import sys
sys.exit(0 if sys.version_info >= (3, 12) else 1)
PY

if ! command -v caddy >/dev/null; then
  say "Installing Caddy from its official apt repository"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -y -q caddy
fi

# --- 2. User, folders, data disk ------------------------------------------------------------------------
say "Creating the $APP_USER user and folders"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$HOME_DIR" --shell /bin/bash "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$HOME_DIR"
install -d -o root -g "$APP_USER" -m 750 "$ENV_DIR"
install -d -m 755 "$DATA_DIR"

if [[ -n "$DATA_DEVICE" ]]; then
  say "Data disk $DATA_DEVICE"
  [[ -b "$DATA_DEVICE" ]] || { echo "$DATA_DEVICE is not a block device. Check the disk name with lsblk."; exit 1; }
  if ! blkid "$DATA_DEVICE" >/dev/null 2>&1; then
    echo "No filesystem on $DATA_DEVICE: formatting it as ext4."
    mkfs.ext4 -q -L clawback-data "$DATA_DEVICE"
  fi
  uuid=$(blkid -s UUID -o value "$DATA_DEVICE")
  grep -q "UUID=$uuid" /etc/fstab || echo "UUID=$uuid $DATA_DIR ext4 defaults,nofail 0 2" >> /etc/fstab
  mountpoint -q "$DATA_DIR" || mount "$DATA_DIR"
fi
chown "$APP_USER:$APP_USER" "$DATA_DIR"
chmod 750 "$DATA_DIR"
install -d -o "$APP_USER" -g "$APP_USER" -m 750 "$DATA_DIR/backups"

# --- 3. Code --------------------------------------------------------------------------------------------
if [[ "$SKIP_CLONE" != "1" ]]; then
  if [[ ! -f "$KEY" ]]; then
    say "Making a deploy key for GitHub"
    install -d -o "$APP_USER" -g "$APP_USER" -m 700 "$HOME_DIR/.ssh"
    as_app ssh-keygen -q -t ed25519 -N "" -C "clawback-vm-deploy" -f "$KEY"
  fi
  as_app bash -c "cat > '$HOME_DIR/.ssh/config'" <<EOF
Host github.com
  IdentityFile $KEY
  IdentitiesOnly yes
  StrictHostKeyChecking yes
EOF
  echo "$GITHUB_HOST_KEY" | as_app bash -c "cat > '$HOME_DIR/.ssh/known_hosts'"
  chmod 600 "$HOME_DIR/.ssh/config" "$HOME_DIR/.ssh/known_hosts"

  if ! as_app git ls-remote "$REPO" >/dev/null 2>&1; then
    say "GitHub doesn't accept the deploy key yet"
    echo "Add this public key to the repo on GitHub: Settings > Deploy keys > Add deploy key."
    echo "Give it a title such as 'clawback-vm' and leave 'Allow write access' unticked."
    echo
    cat "$KEY.pub"
    echo
    echo "Then run this script again."
    exit 2
  fi

  if [[ ! -d "$APP_DIR/.git" ]]; then
    say "Cloning $REPO ($BRANCH)"
    as_app git clone --branch "$BRANCH" "$REPO" "$APP_DIR"
  fi
else
  [[ -f "$APP_DIR/backend/pyproject.toml" ]] || { echo "SKIP_CLONE=1 but $APP_DIR/backend is missing."; exit 1; }
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

# --- 4. Python environment ------------------------------------------------------------------------------
say "Installing the backend into $VENV"
[[ -x "$VENV/bin/python" ]] || as_app python3 -m venv "$VENV"
as_app "$VENV/bin/pip" install -q --upgrade pip
as_app "$VENV/bin/pip" install -q -e "$APP_DIR/backend"

# --- 5. Settings file -----------------------------------------------------------------------------------
if [[ -z "${CLAWBACK_HOST:-}" ]]; then
  ip="${PUBLIC_IP:-$(curl -4 -fsS --max-time 10 https://api.ipify.org || true)}"
  [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Couldn't find the public IP. Set PUBLIC_IP or CLAWBACK_HOST."; exit 1; }
  CLAWBACK_HOST="${ip//./-}.sslip.io"
fi
echo "Host name: $CLAWBACK_HOST"

if [[ ! -f "$ENV_FILE" ]]; then
  say "Creating $ENV_FILE from the template"
  secret=$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
  sed -e "s|__HOST__|$CLAWBACK_HOST|g" -e "s|__SECRET__|$secret|" "$APP_DIR/deploy/vm/clawback.env.example" > "$ENV_FILE"
  chown root:"$APP_USER" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
  NEW_ENV=1
fi

# --- 6. Services ----------------------------------------------------------------------------------------
say "Installing the systemd units"
install -m 644 "$APP_DIR/deploy/vm/clawback.service" /etc/systemd/system/clawback.service
install -m 644 "$APP_DIR/deploy/vm/clawback-nightly.service" /etc/systemd/system/clawback-nightly.service
install -m 644 "$APP_DIR/deploy/vm/clawback-nightly.timer" /etc/systemd/system/clawback-nightly.timer
# Keep request logs short-lived, as the privacy policy says.
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nMaxRetentionSec=14day\n' > /etc/systemd/journald.conf.d/clawback.conf
systemctl restart systemd-journald
systemctl daemon-reload
systemctl enable clawback.service
systemctl restart clawback.service

if as_app bash -c "cd '$APP_DIR/backend' && '$VENV/bin/python' -c 'import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(\"clawback.nightly\") else 1)'"; then
  systemctl enable --now clawback-nightly.timer
else
  echo "clawback.nightly isn't in this branch yet, so the nightly timer stays off. update.sh turns it on later."
fi

say "Configuring Caddy for https://$CLAWBACK_HOST"
sed "s|__HOST__|$CLAWBACK_HOST|g" "$APP_DIR/deploy/vm/Caddyfile" > /etc/caddy/Caddyfile
install -d -o caddy -g caddy /var/log/caddy
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy
systemctl reload-or-restart caddy

# --- 7. Firewall ----------------------------------------------------------------------------------------
say "Opening ports 22, 80 and 443"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

# --- 8. Check -------------------------------------------------------------------------------------------
say "Checking the API"
for _ in $(seq 1 20); do
  curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 1
done
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  echo "The API answers on 127.0.0.1:8000."
else
  echo "The API isn't answering yet. Look at: journalctl -u clawback -n 50"
fi

cat <<EOF

Done.
  Public URL:    https://$CLAWBACK_HOST  (the first HTTPS request can take a few seconds while Caddy gets a certificate)
  Health check:  curl https://$CLAWBACK_HOST/api/health
  Settings:      $ENV_FILE
  Database:      $DATA_DIR
  Logs:          journalctl -u clawback -f
EOF
if [[ "${NEW_ENV:-0}" == "1" ]]; then
  cat <<EOF

Next: put the keys into $ENV_FILE (sudo nano $ENV_FILE), set FRONTEND_ORIGIN to the Vercel URL,
then run: sudo systemctl restart clawback
EOF
fi
