#!/usr/bin/env sh
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing prerequisite: '$1' is not installed or not on PATH." >&2
    exit 1
  }
}

require_file() {
  [ -f "$1" ] || {
    echo "Missing required file: $1" >&2
    exit 1
  }
}

require_command python
require_command npm
require_file requirements.txt
require_file desktop/requirements-build.txt
require_file web/package.json
require_file desktop/package.json

python -m pip install -r requirements.txt -r desktop/requirements-build.txt
(cd web && npm install && npm run build)

if [ -f vay-api.spec ]; then
  SPEC=vay-api.spec
elif [ -f desktop/vay-api.spec ]; then
  SPEC=desktop/vay-api.spec
else
  echo "Missing prerequisite: vay-api.spec was not found at the repo root or in desktop/." >&2
  exit 1
fi
python -m PyInstaller --clean "$SPEC"

if [ "$(uname)" = "Darwin" ]; then
  (cd desktop && npm install && npm run download-mongo && npm run dist:mac)
  echo "Installers: $REPO/desktop/release/"
else
  (cd desktop && npm install && npm run download-mongo && npm run dist)
  echo "Installer: $REPO/desktop/release/Vay-Reports-Setup-3.0.0.exe"
fi
