#!/usr/bin/env bash
# One-time server preparation. Safe to run again; it never overwrites /etc/erf/erf.env.
#
#   sudo bash deploy/scripts/install.sh --domain erf-example.duckdns.org [--mail-env /tmp/erf-mail.env]
#
# It creates the "erf" system user and directories, installs uv, the systemd units and the
# Caddy site file, and validates and reloads Caddy. Other sites served by Caddy are not touched.
#
# --mail-env merges email settings (ERF_MAIL_* and ERF_SMTP_* lines) into /etc/erf/erf.env and then
# deletes that file. The deployment pipeline uses it to pass the email password from GitHub Secrets.
set -euo pipefail

DOMAIN=""
MAIL_ENV=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --mail-env) MAIL_ENV="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "Run this script with sudo." >&2; exit 1; }
[[ -n "$DOMAIN" ]] || { echo "Pass the public host name with --domain." >&2; exit 2; }

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Creating the erf user and directories…"
id erf >/dev/null 2>&1 || useradd --system --home-dir /var/lib/erf --shell /usr/sbin/nologin erf
install -d -m 755 /opt/erf /opt/erf/releases
install -d -m 750 -o erf -g erf /var/lib/erf /var/lib/erf/backups
install -d -m 750 -o root -g erf /etc/erf

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

if [[ ! -f /etc/erf/erf.env ]]; then
  sed "s/ERF_DOMAIN/$DOMAIN/g" "$SRC/env/erf.env.example" > /etc/erf/erf.env
  echo "Wrote /etc/erf/erf.env. Review it, especially the email settings."
else
  echo "Keeping the existing /etc/erf/erf.env."
fi
if [[ -n "$MAIL_ENV" ]]; then
  python3 "$SRC/scripts/merge_env.py" "$MAIL_ENV" /etc/erf/erf.env
  rm -f -- "$MAIL_ENV"
fi
chown root:erf /etc/erf/erf.env
chmod 640 /etc/erf/erf.env

echo "Installing systemd units…"
install -m 644 "$SRC/systemd/erf.service" "$SRC/systemd/erf-backup.service" "$SRC/systemd/erf-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable erf.service erf-backup.timer >/dev/null

echo "Installing the Caddy site for $DOMAIN…"
install -d -m 755 /etc/caddy/sites
sed "s/ERF_DOMAIN/$DOMAIN/g" "$SRC/caddy/erf.caddy" > /etc/caddy/sites/erf.caddy
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl reload caddy

echo
echo "Server prepared. Next, install a release:"
echo "  sudo bash deploy/scripts/release.sh /path/to/erf-<version>.tar.gz [--seed-demo]"
