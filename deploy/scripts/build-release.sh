#!/usr/bin/env bash
# Build a self-contained release archive: backend source, built frontend and deployment files.
# Run from any directory on a machine with Node.js 20+ (the server does not need Node.js).
#
#   deploy/scripts/build-release.sh          # production build
#   deploy/scripts/build-release.sh --demo   # sign-in page lists the demo accounts
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="production"
[[ "${1:-}" == "--demo" ]] && MODE="demo"

VERSION="$(date -u +%Y%m%d%H%M)-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)"
OUT_DIR="$ROOT/release"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "Building frontend ($MODE)…"
( cd "$ROOT/frontend" && npm ci --no-audit --no-fund >/dev/null && \
  if [[ "$MODE" == "demo" ]]; then npm run build:demo >/dev/null; else npm run build >/dev/null; fi )

echo "Staging release $VERSION…"
mkdir -p "$STAGE/backend" "$STAGE/frontend" "$STAGE/deploy"
cp -r "$ROOT/frontend/dist/." "$STAGE/frontend/"
for f in pyproject.toml uv.lock .python-version alembic.ini README.md; do cp "$ROOT/backend/$f" "$STAGE/backend/"; done
cp -r "$ROOT/backend/src" "$ROOT/backend/migrations" "$STAGE/backend/"
cp -r "$ROOT/deploy/." "$STAGE/deploy/"
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "$VERSION ($MODE)" > "$STAGE/VERSION"

mkdir -p "$OUT_DIR"
ARCHIVE="$OUT_DIR/erf-$VERSION.tar.gz"
tar -czf "$ARCHIVE" -C "$STAGE" .
echo "Release archive: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
