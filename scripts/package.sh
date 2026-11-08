#!/usr/bin/env bash
# Builds dist/credential-platform.zip without secrets, databases, caches or the bulky full-dataset JSON/SQL exports.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/credential-platform.zip
cd ..
zip -qr "$(basename "$OLDPWD")/dist/credential-platform.zip" "$(basename "$OLDPWD")" \
  -x "*/.env" "*/instance/*" "*/dist/*" "*/__pycache__/*" "*.pyc" "*/.git/*" "*/node_modules/*" "*.db" "*.db-wal" "*.db-shm" \
     "*/data/full/json/*" "*/data/full/sql/*" "*/.demo_credentials.txt" "*/.test_tmp/*"
ls -lh "$OLDPWD/dist/credential-platform.zip"
