#!/usr/bin/env bash
# Install a release archive built by build-release.sh, with an automatic rollback if the new
# version does not become healthy.
#
#   sudo bash deploy/scripts/release.sh erf-<version>.tar.gz [--seed-demo]
#
# Steps: unpack into /opt/erf/releases/<timestamp>, create the Python environment, back up the
# database, apply migrations, switch /opt/erf/current, restart, check health, keep 5 releases.
set -euo pipefail

ARCHIVE="${1:-}"
SEED_DEMO="no"
[[ "${2:-}" == "--seed-demo" ]] && SEED_DEMO="yes"
[[ $EUID -eq 0 ]] || { echo "Run this script with sudo." >&2; exit 1; }
[[ -f "$ARCHIVE" ]] || { echo "Usage: release.sh <release archive> [--seed-demo]" >&2; exit 2; }
[[ -f /etc/erf/erf.env ]] || { echo "Run install.sh first." >&2; exit 1; }

export UV_PYTHON_INSTALL_DIR=/opt/erf/python
export UV_CACHE_DIR=/opt/erf/.uv-cache
# Use a uv-managed Python so operating system upgrades cannot break the environment.
export UV_PYTHON_PREFERENCE=only-managed
STAMP="$(date -u +%Y%m%d%H%M%S)"
TARGET="/opt/erf/releases/$STAMP"
PREVIOUS="$(readlink -f /opt/erf/current 2>/dev/null || true)"

# Run a command as the service user with the same settings systemd gives the service.
as_erf() {
  runuser -u erf -- bash -c 'umask 027; set -a; . /etc/erf/erf.env; set +a; exec "$@"' _ "$@"
}

echo "Unpacking into $TARGET…"
mkdir -p "$TARGET"
tar -xzf "$ARCHIVE" -C "$TARGET"
echo "Version: $(cat "$TARGET/VERSION")"

echo "Creating the Python environment…"
( cd "$TARGET/backend" && uv sync --frozen --no-dev --quiet )
chmod -R a+rX "$TARGET" /opt/erf/python

if [[ -f /var/lib/erf/erf.db ]]; then
  echo "Backing up the database before migrating…"
  ( cd "$TARGET/backend" && as_erf .venv/bin/erf backup --dest /var/lib/erf/backups --keep 30 )
fi

echo "Applying database migrations…"
( cd "$TARGET/backend" && as_erf .venv/bin/erf migrate )
if [[ "$SEED_DEMO" == "yes" ]]; then
  ( cd "$TARGET/backend" && as_erf .venv/bin/erf seed --demo --force )
else
  ( cd "$TARGET/backend" && as_erf .venv/bin/erf seed )
fi

echo "Switching to the new release…"
ln -sfn "$TARGET" /opt/erf/current.new
mv -T /opt/erf/current.new /opt/erf/current
systemctl restart erf

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8100/api/health >/dev/null 2>&1; then
    echo "Release $STAMP is healthy."
    ls -1dt /opt/erf/releases/*/ | tail -n +6 | xargs -r rm -rf
    exit 0
  fi
  sleep 1
done

echo "The new release did not become healthy. Recent log lines:" >&2
journalctl -u erf -n 30 --no-pager >&2 || true
if [[ -n "$PREVIOUS" && -d "$PREVIOUS" ]]; then
  echo "Rolling back to $PREVIOUS." >&2
  ln -sfn "$PREVIOUS" /opt/erf/current.new
  mv -T /opt/erf/current.new /opt/erf/current
  systemctl restart erf
  echo "If the migration changed the schema, restore the newest file in /var/lib/erf/backups." >&2
fi
exit 1
